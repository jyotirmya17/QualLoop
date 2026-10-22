"""
Decision engine — converts estimate snapshots into recommendations.

ARCHITECTURE BOUNDARY: All decision logic lives in this module ONLY.
Never implement decision rules in API endpoints, database triggers,
or frontend code.

Rules are evaluated in priority order as documented in docs/DECISION_POLICY.md.
The engine is deterministic: identical inputs always produce identical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from domain.enums import ApprovalStatus, DecisionAction
from domain.models import Decision, EstimateSnapshot

POLICY_VERSION = "v0.1.0"


@dataclass
class DecisionPolicy:
    """
    All configurable thresholds for the decision engine.
    Changing any value constitutes a new policy version.
    """

    version: str = POLICY_VERSION
    min_mature_leads_for_reachability: int = 30
    min_mature_contacts_for_qualification: int = 20
    min_maturity_fraction: float = 0.60
    low_reachability_upper_bound: float = 0.25
    low_qualification_upper_bound: float = 0.10
    high_cpql_lower_bound: float = 500.0
    cooldown_hours: float = 48.0
    floor_spend_fraction: float = 0.20
    budget_guardrail_min_spend: float = 100.0
    abnormal_change_threshold: float = 0.30


def evaluate(
    estimate: EstimateSnapshot,
    ad_spend: float,
    policy: DecisionPolicy | None = None,
    prior_decisions: list[Decision] | None = None,
    prior_estimate: Optional[EstimateSnapshot] = None,
) -> Decision:
    """
    Evaluate an estimate snapshot and produce a recommendation.

    Args:
        estimate: Current EstimateSnapshot for the advertisement
        ad_spend: Total spend for this ad (used for budget guardrail check)
        policy: DecisionPolicy to apply (defaults to DecisionPolicy())
        prior_decisions: Previous decisions for this ad (for cooldown check)
        prior_estimate: Previous estimate snapshot (for anomaly detection)

    Returns:
        Decision object with action, reason, and full evidence record

    The function evaluates rules in priority order and returns on first match.
    """
    if policy is None:
        policy = DecisionPolicy()
    if prior_decisions is None:
        prior_decisions = []

    now = datetime.now(timezone.utc)

    # Check cooldown first — if in cooldown, preserve prior decision and return early
    if prior_decisions:
        latest = max(prior_decisions, key=lambda d: d.created_at)
        latest_created = latest.created_at
        if latest_created.tzinfo is None:
            latest_created = latest_created.replace(tzinfo=timezone.utc)
        hours_since = (now - latest_created).total_seconds() / 3600.0
        if (
            hours_since < policy.cooldown_hours
            and latest.action != DecisionAction.CONTINUE_MONITORING
        ):
            # Within cooldown — repeat the monitoring action
            return _make_decision(
                estimate=estimate,
                action=DecisionAction.CONTINUE_MONITORING,
                reason=(
                    f"Cooldown active: previous recommendation '{latest.action.value}' was made "
                    f"{hours_since:.1f} hours ago. Cooldown period is "
                    f"{policy.cooldown_hours:.0f} hours."
                ),
                policy=policy,
                requires_approval=False,
                now=now,
            )

    # Rule 1: Insufficient maturity fraction
    if estimate.maturity_fraction_contact < policy.min_maturity_fraction:
        return _make_decision(
            estimate=estimate,
            action=DecisionAction.FLAG_INSUFFICIENT_EVIDENCE,
            reason=(
                f"Only {estimate.maturity_fraction_contact:.0%} of leads have reached the "
                f"contact maturity window (minimum: {policy.min_maturity_fraction:.0%}). "
                f"Current estimates reflect early data only. "
                f"Pending leads: {estimate.n_leads - estimate.n_mature_leads}."
            ),
            policy=policy,
            requires_approval=False,
            now=now,
        )

    # Rule 2: Insufficient reachability sample size
    if estimate.n_mature_leads < policy.min_mature_leads_for_reachability:
        return _make_decision(
            estimate=estimate,
            action=DecisionAction.COLLECT_MORE_DATA,
            reason=(
                f"Only {estimate.n_mature_leads} mature leads observed. "
                f"Minimum required for reliable reachability estimates: "
                f"{policy.min_mature_leads_for_reachability}."
            ),
            policy=policy,
            requires_approval=False,
            now=now,
        )

    # Rule 3: Insufficient qualification sample size
    if estimate.n_mature_contacts < policy.min_mature_contacts_for_qualification:
        return _make_decision(
            estimate=estimate,
            action=DecisionAction.COLLECT_MORE_DATA,
            reason=(
                f"Only {estimate.n_mature_contacts} contacts with resolved qualification. "
                f"Minimum required: {policy.min_mature_contacts_for_qualification}. "
                f"Reachability evidence ({estimate.n_mature_leads} mature leads) is "
                f"sufficient but intent cannot yet be assessed."
            ),
            policy=policy,
            requires_approval=False,
            now=now,
        )

    # Rule 4: Anomaly detection — abnormal performance change
    if prior_estimate is not None:
        qual_change = _relative_change(
            prior_estimate.qualification_mean,
            estimate.qualification_mean,
        )
        if abs(qual_change) > policy.abnormal_change_threshold:
            direction = "improved" if qual_change > 0 else "declined"
            return _make_decision(
                estimate=estimate,
                action=DecisionAction.FLAG_ABNORMAL_CHANGE,
                reason=(
                    f"Qualification rate has {direction} by "
                    f"{abs(qual_change):.0%} relative to the prior estimate "
                    f"({prior_estimate.qualification_mean:.1%} → "
                    f"{estimate.qualification_mean:.1%}). "
                    f"This may indicate creative fatigue, targeting drift, or a data "
                    f"quality issue. Investigate before acting."
                ),
                policy=policy,
                requires_approval=True,
                now=now,
            )

    # Rule 5: Low reachability (check BEFORE qualification)
    if estimate.reachability_ci_high < policy.low_reachability_upper_bound:
        return _make_decision(
            estimate=estimate,
            action=DecisionAction.INVESTIGATE_LOW_REACHABILITY,
            reason=(
                f"The 90% credible interval for reachability is "
                f"[{estimate.reachability_ci_low:.1%}, {estimate.reachability_ci_high:.1%}], "
                f"entirely below {policy.low_reachability_upper_bound:.0%}. "
                f"This ad generates leads that are difficult to contact. "
                f"Buying intent cannot be reliably assessed until reachability improves. "
                f"Do NOT interpret this as evidence of low intent."
            ),
            policy=policy,
            requires_approval=False,
            now=now,
        )

    # Rule 6: Strong evidence of low qualification (only if reachability is not the problem)
    reachability_ok = estimate.reachability_ci_low >= policy.low_reachability_upper_bound
    if (
        estimate.qualification_ci_high < policy.low_qualification_upper_bound
        and estimate.evidence_sufficient_qualification
        and reachability_ok
    ):
        # Budget guardrail
        if ad_spend < policy.budget_guardrail_min_spend:
            return _make_decision(
                estimate=estimate,
                action=DecisionAction.CONTINUE_MONITORING,
                reason=(
                    f"Qualification rate appears low "
                    f"[{estimate.qualification_ci_low:.1%}, {estimate.qualification_ci_high:.1%}], "
                    f"but ad spend (${ad_spend:.0f}) is below the minimum guardrail "
                    f"(${policy.budget_guardrail_min_spend:.0f}). Increase budget for a "
                    f"statistically meaningful test before considering a pause."
                ),
                policy=policy,
                requires_approval=False,
                now=now,
            )

        return _make_decision(
            estimate=estimate,
            action=DecisionAction.CONSIDER_PAUSE,
            reason=(
                f"With {estimate.n_mature_contacts} resolved contacts, the 90% credible "
                f"interval for qualification rate is "
                f"[{estimate.qualification_ci_low:.1%}, {estimate.qualification_ci_high:.1%}], "
                f"entirely below {policy.low_qualification_upper_bound:.0%}. "
                f"Reachability is adequate "
                f"({estimate.reachability_mean:.1%}), so low intent — not low reachability "
                f"— is the driver. There is strong evidence this ad generates leads with low "
                f"buying intent. Human approval required before any action."
            ),
            policy=policy,
            requires_approval=True,
            now=now,
        )

    # Rule 7: High CPQL
    if (
        not estimate.cpql_unstable
        and estimate.cpql_ci_low is not None
        and estimate.cpql_ci_low > policy.high_cpql_lower_bound
        and estimate.evidence_sufficient_qualification
    ):
        if ad_spend < policy.budget_guardrail_min_spend:
            pass  # fall through to continue_monitoring
        else:
            return _make_decision(
                estimate=estimate,
                action=DecisionAction.CONSIDER_REALLOCATE,
                reason=(
                    f"Estimated cost per qualified lead has a 90% CI lower bound of "
                    f"${estimate.cpql_ci_low:.0f}, exceeding the threshold of "
                    f"${policy.high_cpql_lower_bound:.0f}. "
                    f"Point estimate: ${estimate.cpql_mean:.0f}. "
                    f"Consider reallocating spend to better-performing ads."
                ),
                policy=policy,
                requires_approval=True,
                now=now,
            )

    # Rule 10: Default — continue monitoring
    return _make_decision(
        estimate=estimate,
        action=DecisionAction.CONTINUE_MONITORING,
        reason=(
            f"Sample is mature and sufficient. "
            f"Reachability: {estimate.reachability_mean:.1%} "
            f"[{estimate.reachability_ci_low:.1%}, {estimate.reachability_ci_high:.1%}]. "
            f"Qualification: {estimate.qualification_mean:.1%} "
            f"[{estimate.qualification_ci_low:.1%}, {estimate.qualification_ci_high:.1%}]. "
            f"No strong signal detected. Continue collecting data."
        ),
        policy=policy,
        requires_approval=False,
        now=now,
    )


def _make_decision(
    estimate: EstimateSnapshot,
    action: DecisionAction,
    reason: str,
    policy: DecisionPolicy,
    requires_approval: bool,
    now: datetime,
) -> Decision:
    """Construct a Decision object with full evidence record."""
    approval_status = (
        ApprovalStatus.PENDING if requires_approval else ApprovalStatus.NOT_REQUIRED
    )

    confidence_level = _compute_confidence(estimate)

    return Decision(
        advertisement_id=estimate.advertisement_id,
        estimate_snapshot_id=estimate.id,
        policy_version=policy.version,
        action=action,
        reason=reason,
        supporting_metrics={
            "n_leads": estimate.n_leads,
            "n_mature_leads": estimate.n_mature_leads,
            "n_contacts": estimate.n_contacts,
            "n_mature_contacts": estimate.n_mature_contacts,
            "k_qualified": estimate.k_qualified,
            "maturity_fraction_contact": round(estimate.maturity_fraction_contact, 4),
            "reachability_mean": round(estimate.reachability_mean, 4),
            "reachability_ci_low": round(estimate.reachability_ci_low, 4),
            "reachability_ci_high": round(estimate.reachability_ci_high, 4),
            "qualification_mean": round(estimate.qualification_mean, 4),
            "qualification_ci_low": round(estimate.qualification_ci_low, 4),
            "qualification_ci_high": round(estimate.qualification_ci_high, 4),
            "eql_mean": round(estimate.eql_mean, 2),
            "cpql_mean": round(estimate.cpql_mean, 2) if estimate.cpql_mean else None,
            "cpql_unstable": estimate.cpql_unstable,
            "evidence_sufficient_reachability": estimate.evidence_sufficient_reachability,
            "evidence_sufficient_qualification": estimate.evidence_sufficient_qualification,
            "policy_version": policy.version,
            "thresholds_applied": {
                "min_mature_leads": policy.min_mature_leads_for_reachability,
                "min_mature_contacts": policy.min_mature_contacts_for_qualification,
                "min_maturity_fraction": policy.min_maturity_fraction,
                "low_reachability_upper_bound": policy.low_reachability_upper_bound,
                "low_qualification_upper_bound": policy.low_qualification_upper_bound,
                "high_cpql_lower_bound": policy.high_cpql_lower_bound,
            },
        },
        confidence_level=confidence_level,
        requires_human_approval=requires_approval,
        approval_status=approval_status,
        created_at=now,
    )


def _relative_change(old_value: float, new_value: float) -> float:
    """Compute relative change, handling zero denominator."""
    if abs(old_value) < 1e-9:
        return 0.0
    return (new_value - old_value) / abs(old_value)


def _compute_confidence(estimate: EstimateSnapshot) -> str:
    """Derive a qualitative confidence label from evidence sufficiency."""
    if (
        estimate.evidence_sufficient_reachability
        and estimate.evidence_sufficient_qualification
    ):
        return "high"
    elif estimate.evidence_sufficient_reachability:
        return "medium"
    else:
        return "low"
