"""
Versioned contracts and Pydantic schemas for QualLoop Shadow-Mode Evaluation.

Defines the SHADOW_ECONOMIC_DECISION_LOGGED event contract (v1.0.0), ensuring strict
immutability, privacy protection, and explicit exploratory uncertainty representation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Literal, Optional
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator


class ShadowAction(str, Enum):
    """Possible outcomes of shadow economic evaluation."""
    CONTINUE = "CONTINUE"
    PAUSE = "PAUSE"
    ABSTAIN_INSUFFICIENT_EVIDENCE = "ABSTAIN_INSUFFICIENT_EVIDENCE"
    ABSTAIN_MISSING_ASSUMPTIONS = "ABSTAIN_MISSING_ASSUMPTIONS"
    ERROR = "ERROR"


class BusinessAssumptionStatus(str, Enum):
    """Verification provenance of business valuation inputs."""
    VERIFIED = "VERIFIED"
    PROVISIONAL = "PROVISIONAL"


class ShadowBusinessAssumptions(BaseModel):
    """
    Explicit business inputs required for economic viability calculations.
    Must never be invented or defaulted to an arbitrary universal constant.
    """
    lead_value: Optional[float] = Field(
        default=None,
        description="Expected contribution value per qualified lead (V_QL) in currency units",
    )
    cost_per_lead: float = Field(default=0.0, ge=0.0, description="Variable CRM lead ingestion cost")
    cost_per_call: float = Field(default=0.0, ge=0.0, description="Variable dialer telephony cost per attempt")
    decision_horizon_days: float = Field(default=7.0, gt=0.0, le=90.0, description="Forward decision window in days")
    min_mature_contacts: int = Field(default=20, ge=1, description="Minimum mature contacts required")
    min_maturity_fraction: float = Field(default=0.60, ge=0.0, le=1.0, description="Minimum maturity fraction required")
    confidence_level: float = Field(default=0.90, gt=0.50, lt=1.0, description="Model interval credible level")
    provenance: str = Field(..., min_length=3, description="Source provenance (e.g. CLIENT_FINANCE_UPLOAD, CRM_SYNC)")
    config_version: str = Field(..., min_length=1, description="Version tag of the assumption config")
    status: BusinessAssumptionStatus = Field(
        default=BusinessAssumptionStatus.PROVISIONAL,
        description="Whether assumption is client-verified or provisional",
    )

    @field_validator("lead_value")
    @classmethod
    def validate_lead_value(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("lead_value must be strictly positive if specified")
        return v


class DecisionTimeSnapshot(BaseModel):
    """
    Sanitized snapshot of observable metrics available at decision time.
    Strictly excludes ground truth, future outcomes, and lead-level PII.
    """
    snapshot_id: str = Field(..., description="Snapshot identifier")
    advertisement_id: str = Field(..., description="Advertisement ID evaluated")
    campaign_id: Optional[str] = Field(default=None, description="Campaign ID")
    computed_at: datetime = Field(..., description="UTC timestamp of snapshot computation")
    cumulative_spend: float = Field(..., ge=0.0, description="Accrued spend up to decision time")
    current_day: float = Field(..., ge=0.0, description="Day of observation")
    n_leads: int = Field(..., ge=0, description="Cumulative leads generated")
    n_contacts: int = Field(..., ge=0, description="Cumulative contacts reached")
    n_mature_contacts: int = Field(..., ge=0, description="Contacts past qualification window")
    k_qualified: int = Field(..., ge=0, description="Confirmed qualified leads")
    maturity_fraction_contact: float = Field(..., ge=0.0, le=1.0, description="Fraction of leads past maturity")
    reachability_mean: float = Field(..., ge=0.0, le=1.0, description="Posterior mean reachability")
    qualification_mean: float = Field(..., ge=0.0, le=1.0, description="Posterior mean qualification rate")
    provenance: str = Field(default="TELEMETRY_PIPELINE", description="Origin of telemetry snapshot")

    @field_validator("computed_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class ShadowEconomicDecision(BaseModel):
    """
    Shadow economic recommendation and uncertainty bounds.
    Explicitly carries exploratory calibration status to prevent misrepresenting
    model-derived probabilities as calibrated real-world confidence.
    """
    action: ShadowAction = Field(..., description="Shadow recommendation")
    reason: str = Field(..., min_length=5, description="Auditable reasoning string")
    expected_incremental_spend: Optional[float] = Field(default=None, description="Projected spend over horizon")
    expected_incremental_ql: Optional[float] = Field(default=None, description="Projected qualified leads over horizon")
    expected_incremental_profit: Optional[float] = Field(default=None, description="Projected net contribution profit")
    profit_interval_low: Optional[float] = Field(default=None, description="Lower bound of model-derived interval")
    profit_interval_high: Optional[float] = Field(default=None, description="Upper bound of model-derived interval")
    expected_cpql: Optional[float] = Field(default=None, description="Projected CPQL over horizon")
    breakeven_cpql: Optional[float] = Field(default=None, description="Break-even CPQL threshold given lead value")
    exploratory_probability_profitable: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Model-derived exploratory probability of profitability (uncalibrated)",
    )
    calibration_status: Literal["EXPLORATORY_NOT_CALIBRATED"] = Field(
        default="EXPLORATORY_NOT_CALIBRATED",
        description="Explicit declaration that probabilities are exploratory and uncalibrated",
    )


class ShadowEconomicDecisionLoggedEvent(BaseModel):
    """
    Contract for the versioned SHADOW_ECONOMIC_DECISION_LOGGED event (v1.0.0).

    Strictly non-actioning:
    - is_shadow_only MUST be True.
    - external_action_taken MUST be False.
    - production_action_taken records the actual decision enacted by production heuristic.
    """
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique event UUID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when event was logged",
    )
    schema_version: Literal["1.0.0"] = Field(default="1.0.0", description="Contract schema version")
    evaluator_version: str = Field(..., min_length=1, description="Evaluator implementation version")
    policy_version: str = Field(..., min_length=1, description="Production policy configuration version")

    # Identifiers (Privacy & Tenant Scoping)
    campaign_id: str = Field(..., min_length=1, description="Campaign identifier")
    advertisement_id: str = Field(..., min_length=1, description="Advertisement identifier")
    creative_id: Optional[str] = Field(default=None, description="Creative asset identifier")

    # Input Snapshot & Provenance
    decision_time_snapshot: DecisionTimeSnapshot = Field(..., description="Telemetry snapshot at decision time")
    business_assumptions: Optional[ShadowBusinessAssumptions] = Field(
        default=None,
        description="Business valuation inputs used, or None if missing",
    )

    # Shadow Evaluation Result
    shadow_decision: ShadowEconomicDecision = Field(..., description="Shadow evaluation result")

    # Production Baseline Enacted Concurrently
    production_action_taken: str = Field(..., description="Action enacted by production heuristic (e.g. CONTINUE, PAUSE)")
    production_reason: str = Field(..., description="Reason recorded by production heuristic")

    # Mandatory Guardrails
    is_shadow_only: Literal[True] = Field(
        default=True,
        description="Enforces that this recommendation is strictly non-actioning shadow telemetry",
    )
    external_action_taken: Literal[False] = Field(
        default=False,
        description="Guarantees no outbound mutation was dispatched to external ad platforms",
    )

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def validate_safety_and_language(self) -> ShadowEconomicDecisionLoggedEvent:
        # Enforce that is_shadow_only is True and external_action_taken is False
        if not self.is_shadow_only:
            raise ValueError("Shadow event violation: is_shadow_only must be True")
        if self.external_action_taken:
            raise ValueError("Shadow event violation: external_action_taken must be False")

        # Language Guardrail: Prevent misleading confidence claims when calibration is exploratory
        reason_lower = self.shadow_decision.reason.lower()
        forbidden_phrases = [
            "confidence that it loses money",
            "statistically confirmed",
            "confidence.",
            "confident it loses",
        ]
        for phrase in forbidden_phrases:
            if phrase in reason_lower:
                raise ValueError(
                    f"Misleading uncertainty language detected in shadow reason: '{phrase}' is forbidden "
                    f"under calibration_status='EXPLORATORY_NOT_CALIBRATED'"
                )

        # Explicit check for "95.8% confidence" or similar claims derived from 1 - p
        if "confidence" in reason_lower and "%" in reason_lower:
            # Only allowed if referring to the interval configuration, e.g. "model-derived 90% interval"
            if not ("interval" in reason_lower or "model-derived" in reason_lower):
                raise ValueError(
                    "Forbidden confidence claim detected: cannot convert uncalibrated probabilities to confidence percentages"
                )

        return self
