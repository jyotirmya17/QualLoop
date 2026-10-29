"""
Isolated offline shadow evaluation runner for QualLoop.

Evaluates economic viability on historical snapshots or test fixtures without
affecting production decisions or dispatching any external mutations.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Optional, Tuple

from backend.shadow.contracts import (
    DecisionTimeSnapshot,
    ShadowAction,
    ShadowBusinessAssumptions,
    ShadowEconomicDecision,
    ShadowEconomicDecisionLoggedEvent,
)
from backend.shadow.sink import ShadowEventSink
from backend.shadow.economic_evaluator import (
    EconomicAction,
    EconomicParameters,
    evaluate_ad_economic_viability,
)

logger = logging.getLogger(__name__)


def execute_shadow_evaluation(
    snapshot: Any,
    cumulative_spend: float,
    current_day: float,
    business_assumptions: Optional[ShadowBusinessAssumptions],
    production_action: str,
    production_reason: str,
    sink: ShadowEventSink,
    campaign_id: Optional[str] = None,
    creative_id: Optional[str] = None,
    evaluator_version: str = "economic_evaluator_v1_prototype",
    policy_version: str = "prod_heuristic_v1",
    campaign_tier: Optional[str] = None,
) -> Tuple[str, ShadowEconomicDecisionLoggedEvent]:
    """
    Execute offline shadow economic evaluation on a single snapshot.

    Guarantees:
    1. Returns production_action unchanged (zero mutation of active policy decision).
    2. Idempotently logs a ShadowEconomicDecisionLoggedEvent to the dedicated sink.
    3. Abstains when business_assumptions are missing (never invents lead values).
    4. Records errors explicitly without defaulting to CONTINUE or PAUSE.
    5. Zero outbound network or platform write calls.
    """
    # 1. Build sanitized DecisionTimeSnapshot inside safety envelope
    ad_id = str(getattr(snapshot, "advertisement_id", "unknown_ad"))
    snap_id = str(getattr(snapshot, "id", f"snap-{ad_id}-{current_day}"))
    computed_at = getattr(snapshot, "computed_at", datetime.now(timezone.utc))
    if isinstance(computed_at, str):
        computed_at = datetime.fromisoformat(computed_at)
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)

    mat_frac = getattr(snapshot, "maturity_fraction_contact", getattr(snapshot, "contact_maturity_fraction", 0.0))

    snapshot_error: Optional[Exception] = None
    try:
        decision_snapshot = DecisionTimeSnapshot(
            snapshot_id=snap_id,
            advertisement_id=ad_id,
            campaign_id=campaign_id,
            computed_at=computed_at,
            cumulative_spend=float(cumulative_spend),
            current_day=float(current_day),
            n_leads=int(getattr(snapshot, "n_leads", 0)),
            n_contacts=int(getattr(snapshot, "n_contacts", getattr(snapshot, "k_contacts", 0))),
            n_mature_contacts=int(getattr(snapshot, "n_mature_contacts", 0)),
            k_qualified=int(getattr(snapshot, "k_qualified", 0)),
            maturity_fraction_contact=float(mat_frac),
            reachability_mean=float(getattr(snapshot, "reachability_mean", 0.0)),
            qualification_mean=float(getattr(snapshot, "qualification_mean", 0.0)),
            provenance="OFFLINE_TELEMETRY_FIXTURE",
        )
    except Exception as err:
        logger.exception("Snapshot sanitation error in shadow evaluation")
        snapshot_error = err
        decision_snapshot = DecisionTimeSnapshot(
            snapshot_id=snap_id,
            advertisement_id=ad_id,
            campaign_id=campaign_id,
            computed_at=computed_at,
            cumulative_spend=float(cumulative_spend) if isinstance(cumulative_spend, (int, float)) else 0.0,
            current_day=float(current_day) if isinstance(current_day, (int, float)) else 0.0,
            n_leads=0,
            n_contacts=0,
            n_mature_contacts=0,
            k_qualified=0,
            maturity_fraction_contact=0.0,
            reachability_mean=0.0,
            qualification_mean=0.0,
            provenance="ERROR_FALLBACK_TELEMETRY",
        )

    # 2. Check for snapshot parsing errors or missing business assumptions
    if snapshot_error is not None:
        shadow_decision = ShadowEconomicDecision(
            action=ShadowAction.ERROR,
            reason=f"Shadow economic evaluator snapshot parsing failure: {type(snapshot_error).__name__}: {str(snapshot_error)}",
            calibration_status="EXPLORATORY_NOT_CALIBRATED",
        )
    elif business_assumptions is None or business_assumptions.lead_value is None:
        shadow_decision = ShadowEconomicDecision(
            action=ShadowAction.ABSTAIN_MISSING_ASSUMPTIONS,
            reason=(
                "Shadow economic evaluator abstained: required commercial business input 'lead_value' "
                "(V_QL) is missing or unconfigured. QualLoop strictly forbids guessing a universal constant."
            ),
            calibration_status="EXPLORATORY_NOT_CALIBRATED",
        )
    else:
        # 3. Execute economic evaluator inside a safety envelope
        try:
            econ_params = EconomicParameters(
                lead_value=business_assumptions.lead_value,
                cost_per_lead=business_assumptions.cost_per_lead,
                cost_per_call=business_assumptions.cost_per_call,
                decision_horizon_days=business_assumptions.decision_horizon_days,
                min_mature_contacts=business_assumptions.min_mature_contacts,
                min_maturity_fraction=business_assumptions.min_maturity_fraction,
                confidence_level=business_assumptions.confidence_level,
            )

            res = evaluate_ad_economic_viability(
                snapshot=snapshot,
                cumulative_spend=cumulative_spend,
                current_day=current_day,
                params=econ_params,
                campaign_tier=campaign_tier,
            )

            if res.action == EconomicAction.INSUFFICIENT_EVIDENCE:
                s_action = ShadowAction.ABSTAIN_INSUFFICIENT_EVIDENCE
            elif res.action == EconomicAction.PAUSE:
                s_action = ShadowAction.PAUSE
            else:
                s_action = ShadowAction.CONTINUE

            shadow_decision = ShadowEconomicDecision(
                action=s_action,
                reason=res.reason,
                expected_incremental_spend=res.expected_incremental_spend,
                expected_incremental_ql=res.expected_incremental_ql,
                expected_incremental_profit=res.expected_incremental_profit,
                profit_interval_low=res.profit_ci_low,
                profit_interval_high=res.profit_ci_high,
                expected_cpql=res.expected_cpql if res.expected_cpql != float("inf") else None,
                breakeven_cpql=res.breakeven_cpql,
                exploratory_probability_profitable=res.probability_profitable,
                calibration_status="EXPLORATORY_NOT_CALIBRATED",
            )
        except Exception as err:
            logger.exception("Unexpected error in shadow economic evaluation")
            shadow_decision = ShadowEconomicDecision(
                action=ShadowAction.ERROR,
                reason=f"Shadow economic evaluator runtime failure: {type(err).__name__}: {str(err)}",
                calibration_status="EXPLORATORY_NOT_CALIBRATED",
            )

    # 4. Construct versioned immutable shadow event
    event = ShadowEconomicDecisionLoggedEvent(
        schema_version="1.0.0",
        evaluator_version=evaluator_version,
        policy_version=policy_version,
        campaign_id=campaign_id or "cmp_unspecified",
        advertisement_id=str(ad_id),
        creative_id=creative_id,
        decision_time_snapshot=decision_snapshot,
        business_assumptions=business_assumptions,
        shadow_decision=shadow_decision,
        production_action_taken=production_action,
        production_reason=production_reason,
        is_shadow_only=True,
        external_action_taken=False,
    )

    # 5. Persist to dedicated isolated sink (idempotent)
    sink.record_event(event)

    # 6. Return production action strictly unaltered
    return production_action, event
