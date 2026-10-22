"""
Simulator engine — generates synthetic advertising and lead qualification data.

ARCHITECTURE BOUNDARY: This module is the only place where hidden ground truth
(true_reachability, true_intent) exists. These values must never be passed to
the estimator, decision_engine, or API modules.

The benchmark module accesses ground truth via SimulationResult.ground_truth,
which is only exposed through an explicit benchmark interface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from domain.enums import CallOutcome, LeadStatus, QualificationResult
from domain.models import (
    AdSet,
    Advertisement,
    CallAttempt,
    Campaign,
    Lead,
    QualificationOutcome,
    SimulationRun,
)
from simulator.scenarios import AdConfig, ScenarioConfig

# Simulation epoch — all timestamps are relative offsets from this
_EPOCH = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@dataclass
class AdGroundTruth:
    """Hidden truth for a single advertisement. Benchmark access only."""

    advertisement_id: str
    creative_id: str
    true_reachability: float
    true_intent_by_day: list[float]  # intent may decay due to fatigue
    label: str  # "good", "bad", "mixed"


@dataclass
class SimulationResult:
    """
    Output of a simulation run.

    The `ground_truth` field is intentionally separated from all production
    domain objects. The estimator and decision engine receive only the
    production fields (campaigns, ads, leads, etc.).

    To enforce this boundary in tests: import `SimulationResult` only in
    benchmark/ and tests/. Never import `ground_truth` in estimator/ or
    decision_engine/.
    """

    run: SimulationRun
    campaigns: list[Campaign]
    ad_sets: list[AdSet]
    advertisements: list[Advertisement]
    leads: list[Lead]
    call_attempts: list[CallAttempt]
    qualification_outcomes: list[QualificationOutcome]

    # Benchmark-only — never accessed by estimator or decision engine
    ground_truth: list[AdGroundTruth] = field(default_factory=list)

    def production_view(self) -> "SimulationResult":
        """
        Returns a copy of this result with ground_truth cleared.
        Pass this (not the raw result) to the estimator and decision engine.
        """
        return SimulationResult(
            run=self.run,
            campaigns=self.campaigns,
            ad_sets=self.ad_sets,
            advertisements=self.advertisements,
            leads=self.leads,
            call_attempts=self.call_attempts,
            qualification_outcomes=self.qualification_outcomes,
            ground_truth=[],  # always empty in production view
        )


def run_simulation(config: ScenarioConfig) -> SimulationResult:
    """
    Generate a complete synthetic simulation from the given scenario config.

    Deterministic: same config.seed produces identical output every time.

    Args:
        config: ScenarioConfig with all parameters including hidden ground truth

    Returns:
        SimulationResult with full data + ground_truth (benchmark access only)
    """
    rng = np.random.default_rng(config.seed)

    run_id = str(uuid.UUID(int=int.from_bytes(
        rng.integers(0, 256, size=16, dtype=np.uint8).tobytes()
    )))

    run = SimulationRun(
        id=run_id,
        scenario_name=config.scenario_name,
        seed=config.seed,
        started_at=_EPOCH,
        config=vars(config),
    )

    campaigns: list[Campaign] = []
    ad_sets: list[AdSet] = []
    advertisements: list[Advertisement] = []
    leads: list[Lead] = []
    call_attempts: list[CallAttempt] = []
    qualification_outcomes: list[QualificationOutcome] = []
    ground_truth: list[AdGroundTruth] = []

    for campaign_idx, ad_configs in enumerate(config.ads_per_campaign):
        campaign = Campaign(
            id=_deterministic_id(rng),
            simulation_run_id=run_id,
            name=f"Campaign_{campaign_idx + 1}",
            total_spend=sum(ac.spend for ac in ad_configs),
            created_at=_EPOCH,
        )
        campaigns.append(campaign)

        ad_set = AdSet(
            id=_deterministic_id(rng),
            campaign_id=campaign.id,
            name=f"AdSet_{campaign_idx + 1}_A",
            spend=campaign.total_spend,
        )
        ad_sets.append(ad_set)

        for ad_config in ad_configs:
            ad = Advertisement(
                id=_deterministic_id(rng),
                ad_set_id=ad_set.id,
                creative_id=ad_config.creative_id,
                spend=ad_config.spend,
                impressions=ad_config.impressions,
                clicks=ad_config.clicks,
            )
            advertisements.append(ad)

            # Build per-day intent array (accounts for creative fatigue)
            intent_by_day = _build_intent_by_day(ad_config, config.time_horizon_days)

            ground_truth.append(
                AdGroundTruth(
                    advertisement_id=ad.id,
                    creative_id=ad_config.creative_id,
                    true_reachability=ad_config.true_reachability,
                    true_intent_by_day=intent_by_day,
                    label=ad_config.label,
                )
            )

            # Generate leads over the time horizon
            ad_leads, ad_calls, ad_quals = _generate_ad_funnel(
                rng=rng,
                ad=ad,
                ad_config=ad_config,
                intent_by_day=intent_by_day,
                config=config,
            )
            leads.extend(ad_leads)
            call_attempts.extend(ad_calls)
            qualification_outcomes.extend(ad_quals)

    run.n_campaigns = len(campaigns)
    run.n_ads = len(advertisements)
    run.n_leads = len(leads)
    run.completed_at = _EPOCH + timedelta(days=config.time_horizon_days)

    return SimulationResult(
        run=run,
        campaigns=campaigns,
        ad_sets=ad_sets,
        advertisements=advertisements,
        leads=leads,
        call_attempts=call_attempts,
        qualification_outcomes=qualification_outcomes,
        ground_truth=ground_truth,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deterministic_id(rng: np.random.Generator) -> str:
    """Generate a UUID from the RNG so IDs are deterministic."""
    bytes_ = rng.integers(0, 256, size=16, dtype=np.uint8).tobytes()
    return str(uuid.UUID(bytes=bytes_))


def _build_intent_by_day(ad_config: AdConfig, n_days: int) -> list[float]:
    """
    Compute true intent probability for each simulated day.
    Applies creative fatigue decay if enabled.
    """
    intent = ad_config.true_intent
    result = []
    for day in range(n_days):
        if (
            ad_config.fatigue_enabled
            and day >= ad_config.fatigue_start_day
        ):
            days_into_fatigue = day - ad_config.fatigue_start_day
            # Multiplicative decay: each day reduces intent by fatigue_rate
            decayed = intent * ((1.0 - ad_config.fatigue_rate) ** days_into_fatigue)
            result.append(max(0.001, decayed))
        else:
            result.append(intent)
    return result


def _generate_ad_funnel(
    rng: np.random.Generator,
    ad: Advertisement,
    ad_config: AdConfig,
    intent_by_day: list[float],
    config: ScenarioConfig,
) -> tuple[list[Lead], list[CallAttempt], list[QualificationOutcome]]:
    """
    Generate leads, call attempts, and qualification outcomes for one ad.

    Lead creation follows a Poisson process over the time horizon.
    Call attempts happen within the configured attempt windows.
    Qualification outcomes depend on reachability and intent.
    """
    leads: list[Lead] = []
    calls: list[CallAttempt] = []
    quals: list[QualificationOutcome] = []

    for day in range(config.time_horizon_days):
        # Number of leads created on this day
        n_new_leads = int(rng.poisson(config.leads_per_day_per_ad))
        day_intent = intent_by_day[day]

        for _ in range(n_new_leads):
            # Lead creation time: uniform within the day
            lead_hour = float(rng.uniform(0, 23))
            lead_created_at = _EPOCH + timedelta(days=day, hours=lead_hour)

            lead = Lead(
                id=_deterministic_id(rng),
                advertisement_id=ad.id,
                created_at=lead_created_at,
                status=LeadStatus.SUBMITTED,
            )

            # Simulate call attempts
            lead_calls, was_contacted = _simulate_calls(
                rng=rng,
                lead=lead,
                true_reachability=ad_config.true_reachability,
                config=config,
            )
            calls.extend(lead_calls)

            if was_contacted:
                lead.status = LeadStatus.CONTACTED

                # Simulate qualification
                lead_qual, is_qualified = _simulate_qualification(
                    rng=rng,
                    lead=lead,
                    true_intent=day_intent,
                    contact_time=lead_calls[-1].attempted_at,
                    config=config,
                )
                if lead_qual is not None:
                    quals.append(lead_qual)
                    lead.status = (
                        LeadStatus.QUALIFIED if is_qualified else LeadStatus.DISQUALIFIED
                    )
                else:
                    # Contact happened but qualification window hasn't closed
                    lead.status = LeadStatus.PENDING_QUALIFICATION
            else:
                # Determine if lead is past maturity (and thus truly unreachable)
                lead_age_days = (
                    _EPOCH + timedelta(days=config.time_horizon_days)
                    - lead_created_at
                ).total_seconds() / 86400
                if lead_age_days >= config.contact_maturity_days:
                    lead.status = LeadStatus.PENDING_CONTACT  # mature, never reached
                else:
                    lead.status = LeadStatus.PENDING_CONTACT  # still in window

            leads.append(lead)

    return leads, calls, quals


def _simulate_calls(
    rng: np.random.Generator,
    lead: Lead,
    true_reachability: float,
    config: ScenarioConfig,
) -> tuple[list[CallAttempt], bool]:
    """
    Simulate call attempts for a single lead.

    Returns (call_attempts, was_contacted).
    Contact happens with probability true_reachability overall,
    distributed across max_call_attempts tries.
    """
    calls: list[CallAttempt] = []
    was_contacted = False

    # Determine if this lead will eventually be reachable
    will_be_reached = rng.random() < true_reachability

    for attempt_num in range(config.max_call_attempts):
        if was_contacted:
            break

        # Time of this attempt
        hours_offset = (
            config.first_call_attempt_mean_hours
            + attempt_num * config.retry_interval_hours
            + float(rng.normal(0, 2.0))  # small noise
        )
        attempt_time = lead.created_at + timedelta(hours=max(0.5, hours_offset))

        if will_be_reached and attempt_num == config.max_call_attempts - 1:
            # Last attempt succeeds if lead is reachable
            outcome = CallOutcome.ANSWERED
            was_contacted = True
        elif will_be_reached and rng.random() < (0.4 * (attempt_num + 1)):
            # Earlier attempt may also succeed
            outcome = CallOutcome.ANSWERED
            was_contacted = True
        else:
            # Failed attempt — choose from string values to avoid numpy str_ coercion
            _fail_outcomes = ["no_answer", "voicemail", "disconnected"]
            outcome = CallOutcome(str(rng.choice(_fail_outcomes, p=[0.60, 0.30, 0.10])))

        calls.append(
            CallAttempt(
                id=_deterministic_id(rng),
                lead_id=lead.id,
                attempted_at=attempt_time,
                outcome=outcome,
            )
        )

    return calls, was_contacted


def _simulate_qualification(
    rng: np.random.Generator,
    lead: Lead,
    true_intent: float,
    contact_time: datetime,
    config: ScenarioConfig,
) -> tuple[Optional[QualificationOutcome], bool]:
    """
    Simulate qualification outcome for a contacted lead.

    Returns (QualificationOutcome | None, is_qualified).
    Returns None if the qualification window hasn't closed by end of simulation.
    """
    # Qualification resolution time: after a delay from contact
    resolution_days = float(rng.exponential(scale=3.0))  # most resolve in a few days
    resolved_at = contact_time + timedelta(days=resolution_days)

    # Check if resolution falls within the simulation horizon
    sim_end = _EPOCH + timedelta(days=config.time_horizon_days)
    if resolved_at > sim_end:
        return None, False  # outcome pending — simulation ended first

    is_qualified = rng.random() < true_intent
    result = QualificationResult.QUALIFIED if is_qualified else QualificationResult.DISQUALIFIED

    return (
        QualificationOutcome(
            id=_deterministic_id(rng),
            lead_id=lead.id,
            resolved_at=resolved_at,
            result=result,
        ),
        is_qualified,
    )
