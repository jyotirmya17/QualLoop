"""
Shared campaign evaluation and audit persistence service.

Enforces architecture rules:
- Estimates computed using pure domain models in estimator/
- Decisions evaluated using deterministic rules in decision_engine/
- Decisions and audit events persisted atomically via audit.trail / persistence
- Idempotent: repeated evaluation does not duplicate records in decisions or audit_events
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from api.schemas.responses import (
    AdAnalysisOut,
    AdvertisementOut,
    CampaignSummaryOut,
    DecisionOut,
    EstimateSnapshotOut,
)
from api.store import get as get_simulation_run
from audit.trail import query_decisions, record_decisions
from decision_engine.engine import DecisionPolicy, evaluate_campaign
from domain.models import Decision
from estimator.estimator import EstimatorConfig, compute_campaign_estimates
from simulator.engine import SimulationResult

_DEFAULT_CONFIG = EstimatorConfig()
_DEFAULT_POLICY = DecisionPolicy()


def compute_analysis_for_run(
    result: SimulationResult,
    policy: Optional[DecisionPolicy] = None,
) -> tuple[list[CampaignSummaryOut], list[Decision]]:
    """
    Compute Bayesian estimates and policy decisions for all ads in a simulation run.
    Does NOT mutate database. Attaches simulation_run_id to all evaluated Decision models.
    """
    active_policy = policy or _DEFAULT_POLICY

    # Index domain objects by advertisement_id
    leads_by_ad: dict[str, list] = defaultdict(list)
    calls_by_ad: dict[str, list] = defaultdict(list)
    quals_by_ad: dict[str, list] = defaultdict(list)

    for lead in result.leads:
        leads_by_ad[lead.advertisement_id].append(lead)

    lead_id_set = {l.id for l in result.leads}
    leads_by_id = {l.id: l for l in result.leads}

    for ca in result.call_attempts:
        if ca.lead_id in lead_id_set:
            ad_id = leads_by_id[ca.lead_id].advertisement_id
            calls_by_ad[ad_id].append(ca)

    for qo in result.qualification_outcomes:
        if qo.lead_id in lead_id_set:
            ad_id = leads_by_id[qo.lead_id].advertisement_id
            quals_by_ad[ad_id].append(qo)

    # Index ads by campaign (via ad_sets)
    ad_set_to_campaign = {ads.id: ads.campaign_id for ads in result.ad_sets}
    ads_by_campaign: dict[str, list] = defaultdict(list)
    for ad in result.advertisements:
        campaign_id = ad_set_to_campaign.get(ad.ad_set_id, "unknown")
        ads_by_campaign[campaign_id].append(ad)

    summaries: list[CampaignSummaryOut] = []
    all_decisions: list[Decision] = []

    for campaign in result.campaigns:
        campaign_ads = ads_by_campaign.get(campaign.id, [])
        ads_data = [
            (
                ad,
                leads_by_ad.get(ad.id, []),
                calls_by_ad.get(ad.id, []),
                quals_by_ad.get(ad.id, []),
            )
            for ad in campaign_ads
        ]
        snapshots = compute_campaign_estimates(
            ads_data=ads_data,
            observation_time=result.run.completed_at,
            config=_DEFAULT_CONFIG,
            seed=result.run.seed,
        )
        ad_spends = {ad.id: ad.spend for ad in campaign_ads}
        decisions = evaluate_campaign(
            snapshots=snapshots,
            ad_spends=ad_spends,
            policy=active_policy,
        )

        ad_analyses = []
        for ad, snapshot, decision in zip(campaign_ads, snapshots, decisions):
            # Explicitly attach simulation_run_id to decision
            decision.simulation_run_id = result.run.id
            all_decisions.append(decision)

            ad_analyses.append(
                AdAnalysisOut(
                    advertisement=AdvertisementOut(
                        id=ad.id,
                        ad_set_id=ad.ad_set_id,
                        creative_id=ad.creative_id,
                        spend=ad.spend,
                        impressions=ad.impressions,
                        clicks=ad.clicks,
                    ),
                    estimate=EstimateSnapshotOut(**snapshot.model_dump()),
                    decision=DecisionOut(**decision.model_dump()),
                )
            )

        summaries.append(
            CampaignSummaryOut(
                campaign_id=campaign.id,
                campaign_name=campaign.name,
                total_spend=campaign.total_spend,
                n_ads=len(campaign_ads),
                ads=ad_analyses,
            )
        )

    return summaries, all_decisions


def evaluate_and_persist_run(
    run_id: str,
    policy: Optional[DecisionPolicy] = None,
) -> list[CampaignSummaryOut]:
    """
    Explicit, idempotent POST action to evaluate a simulation run and persist decisions + audit events.
    Guarantees no duplicate records are created if invoked multiple times.
    """
    result = get_simulation_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Simulation run '{run_id}' not found")

    active_policy = policy or _DEFAULT_POLICY
    summaries, decisions = compute_analysis_for_run(result, active_policy)

    # Check if decisions for this run and policy version are already persisted
    existing = query_decisions(
        simulation_run_id=run_id,
        limit=1000,
    )
    existing_by_ad = {
        d.advertisement_id: d for d in existing if d.policy_version == active_policy.version
    }

    if existing_by_ad:
        # Already persisted — map persisted decisions onto the summaries
        return _apply_persisted_decisions_to_summaries(summaries, existing_by_ad)

    # Not yet persisted — attempt atomic insertion
    try:
        record_decisions(decisions)
    except IntegrityError:
        # Race condition handled by database uniqueness constraint uq_decisions_run_ad_policy
        rechecked = query_decisions(simulation_run_id=run_id, limit=1000)
        rechecked_by_ad = {
            d.advertisement_id: d for d in rechecked if d.policy_version == active_policy.version
        }
        return _apply_persisted_decisions_to_summaries(summaries, rechecked_by_ad)

    decisions_by_ad = {d.advertisement_id: d for d in decisions}
    return _apply_persisted_decisions_to_summaries(summaries, decisions_by_ad)


def get_or_compute_analysis(
    run_id: str,
    policy: Optional[DecisionPolicy] = None,
) -> list[CampaignSummaryOut]:
    """
    Read-only retrieval of campaign analysis for a simulation run.
    Uses existing persisted decisions if available; computes without database mutation if not.
    """
    result = get_simulation_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Simulation run '{run_id}' not found")

    active_policy = policy or _DEFAULT_POLICY
    summaries, _ = compute_analysis_for_run(result, active_policy)

    # Check for persisted decisions in durable storage
    existing = query_decisions(simulation_run_id=run_id, limit=1000)
    existing_by_ad = {
        d.advertisement_id: d for d in existing if d.policy_version == active_policy.version
    }

    if existing_by_ad:
        return _apply_persisted_decisions_to_summaries(summaries, existing_by_ad)

    return summaries


def _apply_persisted_decisions_to_summaries(
    summaries: list[CampaignSummaryOut],
    persisted_by_ad: dict[str, Decision],
) -> list[CampaignSummaryOut]:
    """Substitute transient decisions with their authoritative persisted records."""
    for camp_summary in summaries:
        for ad_analysis in camp_summary.ads:
            ad_id = ad_analysis.advertisement.id
            if ad_id in persisted_by_ad:
                persisted_dec = persisted_by_ad[ad_id]
                dec_data = persisted_dec.model_dump()
                dec_data["is_persisted"] = True
                ad_analysis.decision = DecisionOut(**dec_data)
    return summaries
