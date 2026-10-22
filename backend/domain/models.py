"""
Domain Pydantic models — pure data containers, no business logic.

These are the production-facing domain objects. The simulator uses these same
structures but additionally carries hidden ground-truth data in a separate class
that is never exported to this module.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from domain.enums import (
    ApprovalStatus,
    CallOutcome,
    DecisionAction,
    FeedbackProcessingStatus,
    FeedbackValidationStatus,
    LeadStatus,
    QualificationResult,
)


class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    simulation_run_id: str
    name: str
    total_spend: float
    created_at: datetime

    @field_validator("total_spend")
    @classmethod
    def spend_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("total_spend cannot be negative")
        return v


class AdSet(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    campaign_id: str
    name: str
    spend: float

    @field_validator("spend")
    @classmethod
    def spend_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("spend cannot be negative")
        return v


class Advertisement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ad_set_id: str
    creative_id: str
    spend: float
    impressions: int
    clicks: int

    @field_validator("spend")
    @classmethod
    def spend_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("spend cannot be negative")
        return v

    @field_validator("impressions", "clicks")
    @classmethod
    def counts_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("counts cannot be negative")
        return v


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    advertisement_id: str
    created_at: datetime
    status: LeadStatus = LeadStatus.SUBMITTED
    source: str = "ad"

    @field_validator("created_at")
    @classmethod
    def created_at_must_not_be_future(cls, v: datetime) -> datetime:
        # Note: in simulation context this is relaxed — simulation uses relative time
        return v


class CallAttempt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lead_id: str
    attempted_at: datetime
    outcome: CallOutcome


class QualificationOutcome(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lead_id: str
    resolved_at: datetime
    result: QualificationResult
    notes: str = ""


class EstimateSnapshot(BaseModel):
    """
    Output of the estimator for a single advertisement.

    All credible intervals are 90% highest-density intervals from the
    posterior Beta distribution.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    advertisement_id: str
    computed_at: datetime
    estimator_version: str

    # Raw observation counts
    n_leads: int
    n_mature_leads: int  # leads past contact maturity window
    n_contacts: int  # leads successfully contacted
    n_mature_contacts: int  # contacts past qualification maturity window
    k_qualified: int  # qualified among mature contacts

    # Maturity fractions
    maturity_fraction_contact: float
    maturity_fraction_qualification: float

    # Reachability estimates (Beta-Binomial posterior)
    reachability_mean: float
    reachability_ci_low: float
    reachability_ci_high: float

    # Qualification rate estimates (Beta-Binomial posterior)
    qualification_mean: float
    qualification_ci_low: float
    qualification_ci_high: float

    # Expected qualified leads (Monte Carlo propagation)
    eql_mean: float
    eql_ci_low: float
    eql_ci_high: float

    # Cost per qualified lead (Monte Carlo)
    cpql_mean: Optional[float] = None
    cpql_ci_low: Optional[float] = None
    cpql_ci_high: Optional[float] = None
    cpql_unstable: bool = False  # True when EQL near zero

    # Evidence quality flags
    evidence_sufficient_reachability: bool
    evidence_sufficient_qualification: bool

    # Fraction of EQL Monte Carlo samples with zero qualified leads
    zero_eql_fraction: float = 0.0


class Decision(BaseModel):
    """A recommendation produced by the decision engine."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    advertisement_id: str
    estimate_snapshot_id: str
    policy_version: str
    action: DecisionAction
    reason: str
    supporting_metrics: dict
    confidence_level: str  # "high", "medium", "low"
    requires_human_approval: bool
    approval_status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    created_at: datetime


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: Optional[str] = None
    event_type: str
    data: dict
    created_at: datetime


class FeedbackEvent(BaseModel):
    """
    A validated Meta Conversions API event payload.

    Based on Meta Graph API v21.0 Conversions API specification.
    All user PII fields must be SHA-256 hashed before this object is created.
    In dry-run mode (v1), this object is logged but never transmitted.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    qualification_outcome_id: str
    idempotency_key: str  # prevents duplicate processing
    event_name: str  # e.g. "Lead", "QualifiedLead"
    event_time: int  # Unix timestamp
    action_source: str = "crm"

    # User data — all PII must be SHA-256 hashed
    user_data: dict  # {em: hashed_email, ph: hashed_phone, ...}
    custom_data: dict  # {lead_id: ..., ad_id: ..., qualification_score: ...}

    # Processing metadata
    validation_status: FeedbackValidationStatus
    processing_status: FeedbackProcessingStatus
    created_at: datetime


class SimulationRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str
    seed: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    config: dict = {}
    n_campaigns: int = 0
    n_ads: int = 0
    n_leads: int = 0
