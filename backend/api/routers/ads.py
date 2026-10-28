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
from api.evaluation import evaluate_and_persist_run, get_or_compute_analysis
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
    Pure read-only operation: attaches persisted decisions if evaluated,
    or transient calculations without database mutation if not evaluated.
    """
    return get_or_compute_analysis(run_id)


@router.post("/run/{run_id}/evaluate", response_model=list[CampaignSummaryOut])
def evaluate_run_analysis(run_id: str):
    """
    Explicit, idempotent evaluation of a simulation run.
    Persists decisions and audit events to durable storage.
    """
    return evaluate_and_persist_run(run_id)
