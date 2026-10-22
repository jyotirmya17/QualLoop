"""
Ads router.

GET /ads/run/{run_id}       — get all ad analyses for a simulation run
GET /ads/{ad_id}/estimate   — get the latest estimate for one ad
GET /ads/{ad_id}/recommend  — get the latest recommendation for one ad
"""

from __future__ import annotations

from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from api.schemas.responses import (
    AdAnalysisOut, AdvertisementOut, CampaignSummaryOut,
    EstimateSnapshotOut, DecisionOut,
)
from api.store import get, list_runs
from estimator.estimator import compute_estimates, EstimatorConfig
from decision_engine.engine import evaluate, DecisionPolicy

router = APIRouter()

_DEFAULT_CONFIG = EstimatorConfig()
_DEFAULT_POLICY = DecisionPolicy()


def _build_ad_analysis(
    ad,
    leads: list,
    call_attempts: list,
    qual_outcomes: list,
    seed: int | None = None,
    observation_time: datetime | None = None,
) -> AdAnalysisOut:
    """Compute estimate + decision for one ad using current simulation state."""
    obs_time = observation_time or datetime.now(timezone.utc)

    snapshot = compute_estimates(
        advertisement=ad,
        leads=leads,
        call_attempts=call_attempts,
        qualification_outcomes=qual_outcomes,
        observation_time=obs_time,
        config=_DEFAULT_CONFIG,
        seed=seed,
    )
    decision = evaluate(snapshot, ad_spend=ad.spend, policy=_DEFAULT_POLICY)

    return AdAnalysisOut(
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


@router.get("/run/{run_id}", response_model=list[CampaignSummaryOut])
def get_run_analysis(run_id: str):
    """
    Get full analysis for all campaigns and ads in a simulation run.

    Returns a list of CampaignSummaryOut, each containing per-ad estimates
    and recommendations. Note: this computes estimates at request time —
    in production this would be a read from a pre-computed table.
    """
    result = get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Simulation run '{run_id}' not found")

    # Index domain objects by ad_id
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
    campaign_map = {c.id: c for c in result.campaigns}
    ads_by_campaign: dict[str, list] = defaultdict(list)
    for ad in result.advertisements:
        campaign_id = ad_set_to_campaign.get(ad.ad_set_id, "unknown")
        ads_by_campaign[campaign_id].append(ad)

    summaries = []
    for campaign in result.campaigns:
        campaign_ads = ads_by_campaign.get(campaign.id, [])
        ad_analyses = []
        for ad in campaign_ads:
            analysis = _build_ad_analysis(
                ad=ad,
                leads=leads_by_ad.get(ad.id, []),
                call_attempts=calls_by_ad.get(ad.id, []),
                qual_outcomes=quals_by_ad.get(ad.id, []),
                seed=result.run.seed,
                observation_time=result.run.completed_at,
            )
            ad_analyses.append(analysis)

        summaries.append(CampaignSummaryOut(
            campaign_id=campaign.id,
            campaign_name=campaign.name,
            total_spend=campaign.total_spend,
            n_ads=len(campaign_ads),
            ads=ad_analyses,
        ))

    return summaries
