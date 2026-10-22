"""API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from domain.enums import DecisionAction, ApprovalStatus


class SimulationRunOut(BaseModel):
    id: str
    scenario_name: str
    seed: int
    started_at: datetime
    completed_at: Optional[datetime]
    n_campaigns: int
    n_ads: int
    n_leads: int


class AdvertisementOut(BaseModel):
    id: str
    ad_set_id: str
    creative_id: str
    spend: float
    impressions: int
    clicks: int


class EstimateSnapshotOut(BaseModel):
    id: str
    advertisement_id: str
    computed_at: datetime
    estimator_version: str
    n_leads: int
    n_mature_leads: int
    n_contacts: int
    n_mature_contacts: int
    k_qualified: int
    maturity_fraction_contact: float
    maturity_fraction_qualification: float
    reachability_mean: float
    reachability_ci_low: float
    reachability_ci_high: float
    qualification_mean: float
    qualification_ci_low: float
    qualification_ci_high: float
    eql_mean: float
    eql_ci_low: float
    eql_ci_high: float
    cpql_mean: Optional[float]
    cpql_ci_low: Optional[float]
    cpql_ci_high: Optional[float]
    cpql_unstable: bool
    evidence_sufficient_reachability: bool
    evidence_sufficient_qualification: bool
    zero_eql_fraction: float


class DecisionOut(BaseModel):
    id: str
    advertisement_id: str
    estimate_snapshot_id: str
    policy_version: str
    action: DecisionAction
    reason: str
    supporting_metrics: dict
    confidence_level: str
    requires_human_approval: bool
    approval_status: ApprovalStatus
    created_at: datetime


class AdAnalysisOut(BaseModel):
    """Combined estimate + decision for one ad."""
    advertisement: AdvertisementOut
    estimate: EstimateSnapshotOut
    decision: DecisionOut
    simulated_data_warning: str = "SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT"


class RunSimulationIn(BaseModel):
    scenario_name: str = "healthy_campaign"
    seed: int = 42


class CampaignSummaryOut(BaseModel):
    campaign_id: str
    campaign_name: str
    total_spend: float
    n_ads: int
    ads: list[AdAnalysisOut]
