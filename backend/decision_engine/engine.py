"""
Decision engine — converts estimate snapshots into recommendations.

ARCHITECTURE BOUNDARY: All decision logic lives in this module ONLY.
Never implement decision rules in API endpoints, database triggers,
or frontend code.

Rules are evaluated in priority order as documented in docs/DECISION_POLICY.md.
The engine is deterministic: identical inputs always produce identical outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.enums import ApprovalStatus, DecisionAction, DecisionTier
from domain.models import Decision, EstimateSnapshot

POLICY_VERSION = "v0.2.0"


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
    target_cpql: float = 75.0
    cooldown_hours: float = 48.0
    floor_spend_fraction: float = 0.20
    budget_guardrail_min_spend: float = 100.0
    abnormal_change_threshold: float = 0.30
    spend_shift_cap_fraction: float = 0.25
    guardrail_action_spend_cap: float = 500.0


def _determine_tier_and_auto_applied(
    action: DecisionAction,
    ad_spend: float,
    policy: DecisionPolicy,
) -> tuple[str, bool, bool]:
    """
    Derive (tier, auto_applied, requires_approval) based on action and spend guardrails.

    Execution Semantics:
    - 'tier': Governance level ('gated' | 'within_guardrails' | 'autonomous').
    - 'auto_applied': Boolean flag indicating whether the recommendation is pre-approved
      for autonomous execution under policy spend guardrails without human intervention.
      NOTE: In the current release, QualLoop acts as an advisory decision intelligence system;
      it produces recommendations and simulated outcomes, and does not execute mutations
      against live advertising APIs.
    - 'requires_approval': True when human sign-off is mandatory before action.

    Rules:
    - Raising budget and launching: ALWAYS tier=gated and auto_applied=false.
    - Pausing and reallocating / shifting spend: ALWAYS tier=within_guardrails.
      auto_applied=true if ad_spend <= policy.guardrail_action_spend_cap, else false.
    - Observational / monitoring: tier=autonomous and auto_applied=true.
    """
    if action in (DecisionAction.RAISE_BUDGET, DecisionAction.LAUNCH_AD):
        return (DecisionTier.GATED.value, False, True)
    elif action == DecisionAction.FLAG_ABNORMAL_CHANGE:
        return (DecisionTier.GATED.value, False, True)
    elif action in (
        DecisionAction.PAUSE_AD,
        DecisionAction.REALLOCATE_BUDGET,
        DecisionAction.SHIFT_SPEND,
    ):
        is_under_cap = ad_spend <= policy.guardrail_action_spend_cap
        return (DecisionTier.WITHIN_GUARDRAILS.value, is_under_cap, not is_under_cap)
    elif action in (
        DecisionAction.CONSIDER_PAUSE,
        DecisionAction.CONSIDER_REALLOCATE,
    ):
        return (DecisionTier.WITHIN_GUARDRAILS.value, False, True)
    else:
        return (DecisionTier.AUTONOMOUS.value, True, False)


def evaluate(
    estimate: EstimateSnapshot,
    ad_spend: float,
    policy: DecisionPolicy | None = None,
    prior_decisions: list[Decision] | None = None,
    prior_estimate: Optional[EstimateSnapshot] = None,
    campaign_snapshots: list[EstimateSnapshot] | None = None,
) -> Decision:
    """
    Evaluate an estimate snapshot and produce a recommendation.

    Args:
        estimate: Current EstimateSnapshot for the advertisement
        ad_spend: Total spend for this ad (used for budget guardrail check)
        policy: DecisionPolicy to apply (defaults to DecisionPolicy())
        prior_decisions: Previous decisions for this ad (for cooldown check)
        prior_estimate: Previous estimate snapshot (for anomaly detection)
        campaign_snapshots: Optional snapshots of all ads in campaign (for relative cross-ad rules)

    Returns:
        Decision object with action, tier, auto_applied, reason, and full evidence record

    The function evaluates rules in priority order and returns on first match.
    """
    if policy is None:
        policy = DecisionPolicy()
    if prior_decisions is None:
        prior_decisions = []

    now = datetime.now(timezone.utc)
    ci_pct = int(round(estimate.ci_level * 100)) if getattr(estimate, "ci_level", None) else 90

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
            return _make_decision(
                estimate=estimate,
                ad_spend=ad_spend,
                action=DecisionAction.CONTINUE_MONITORING,
                reason=(
                    f"Cooldown active: previous recommendation '{latest.action.value}' was made "
                    f"{hours_since:.1f} hours ago (less than {policy.cooldown_hours:.0f}h limit). "
                    f"Maintaining autonomous monitoring."
                ),
                policy=policy,
                now=now,
            )

    # Rule 1: Insufficient maturity fraction
    if estimate.maturity_fraction_contact < policy.min_maturity_fraction:
        pending_leads = estimate.n_leads - estimate.n_mature_leads
        return _make_decision(
            estimate=estimate,
            ad_spend=ad_spend,
            action=DecisionAction.FLAG_INSUFFICIENT_EVIDENCE,
            reason=(
                f"Maturity fraction for ad '{estimate.advertisement_id}' is {estimate.maturity_fraction_contact:.1%}, "
                f"which is below the required {policy.min_maturity_fraction:.1%} threshold. Only {estimate.n_mature_leads} "
                f"of {estimate.n_leads} leads have aged past contact maturity window (pending leads: {pending_leads}). "
                f"Autonomous data collection in progress."
            ),
            policy=policy,
            now=now,
        )

    # Rule 2: Insufficient reachability sample size
    if estimate.n_mature_leads < policy.min_mature_leads_for_reachability:
        return _make_decision(
            estimate=estimate,
            ad_spend=ad_spend,
            action=DecisionAction.COLLECT_MORE_DATA,
            reason=(
                f"Observed {estimate.n_mature_leads} mature leads for ad '{estimate.advertisement_id}', "
                f"below required threshold of {policy.min_mature_leads_for_reachability}. "
                f"Reachability rate cannot be evaluated reliably yet."
            ),
            policy=policy,
            now=now,
        )

    # Rule 3: Insufficient qualification sample size
    if estimate.n_mature_contacts < policy.min_mature_contacts_for_qualification:
        return _make_decision(
            estimate=estimate,
            ad_spend=ad_spend,
            action=DecisionAction.COLLECT_MORE_DATA,
            reason=(
                f"Observed {estimate.n_mature_contacts} mature contacts ({estimate.k_qualified} qualified) for ad '{estimate.advertisement_id}', "
                f"below required threshold of {policy.min_mature_contacts_for_qualification}. "
                f"Reachability sample ({estimate.n_mature_leads} mature leads) is sufficient, but qualification intent cannot yet be assessed."
            ),
            policy=policy,
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
                ad_spend=ad_spend,
                action=DecisionAction.FLAG_ABNORMAL_CHANGE,
                reason=(
                    f"Qualification rate for ad '{estimate.advertisement_id}' has {direction} by "
                    f"{abs(qual_change):.1%} relative to the prior estimate "
                    f"({prior_estimate.qualification_mean:.1%} → {estimate.qualification_mean:.1%}), "
                    f"exceeding abnormal change threshold {policy.abnormal_change_threshold:.1%}. "
                    f"Gated human review required before acting."
                ),
                policy=policy,
                now=now,
            )

    # Rule 5: Low reachability (check BEFORE qualification)
    if estimate.reachability_ci_high < policy.low_reachability_upper_bound:
        return _make_decision(
            estimate=estimate,
            ad_spend=ad_spend,
            action=DecisionAction.INVESTIGATE_LOW_REACHABILITY,
            reason=(
                f"The {ci_pct}% credible interval for reachability on ad '{estimate.advertisement_id}' is "
                f"[{estimate.reachability_ci_low:.1%}, {estimate.reachability_ci_high:.1%}] (mean {estimate.reachability_mean:.1%}), "
                f"entirely below {policy.low_reachability_upper_bound:.1%}. "
                f"Generated {estimate.n_contacts}/{estimate.n_mature_leads} contacts. "
                f"Buying intent cannot be assessed until contact cadence improves. Do not misinterpret as low intent."
            ),
            policy=policy,
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
                ad_spend=ad_spend,
                action=DecisionAction.CONTINUE_MONITORING,
                reason=(
                    f"Qualification rate interval [{estimate.qualification_ci_low:.1%}, {estimate.qualification_ci_high:.1%}] "
                    f"(mean {estimate.qualification_mean:.1%}) is low, but ad spend (₹{ad_spend:.2f}) is below minimum "
                    f"guardrail (₹{policy.budget_guardrail_min_spend:.2f}). Continue monitoring to reach statistical significance."
                ),
                policy=policy,
                now=now,
            )

        is_under_cap = ad_spend <= policy.guardrail_action_spend_cap
        action = DecisionAction.PAUSE_AD if is_under_cap else DecisionAction.CONSIDER_PAUSE
        action_verb = "Recommending guardrailed pause (auto-applicable under spend cap)" if is_under_cap else "Recommending pause for human review"
        return _make_decision(
            estimate=estimate,
            ad_spend=ad_spend,
            action=action,
            reason=(
                f"With {estimate.n_mature_contacts} mature contacts ({estimate.k_qualified} qualified), the {ci_pct}% credible "
                f"interval for qualification rate is [{estimate.qualification_ci_low:.1%}, {estimate.qualification_ci_high:.1%}], "
                f"sitting entirely below threshold {policy.low_qualification_upper_bound:.1%}. Reachability is adequate "
                f"({estimate.reachability_mean:.1%}), confirming poor buying intent. "
                f"{action_verb} (spend: ₹{ad_spend:.2f}, guardrail cap: ₹{policy.guardrail_action_spend_cap:.2f})."
            ),
            policy=policy,
            now=now,
        )

    # Rule 7: Relative rule across campaign ads (spend-shift recommendation)
    if (
        campaign_snapshots
        and not estimate.cpql_unstable
        and estimate.cpql_ci_low is not None
        and estimate.evidence_sufficient_qualification
        and ad_spend >= policy.budget_guardrail_min_spend
    ):
        for other in campaign_snapshots:
            if (
                other.advertisement_id != estimate.advertisement_id
                and not other.cpql_unstable
                and other.cpql_ci_high is not None
                and other.evidence_sufficient_qualification
            ):
                if estimate.cpql_ci_low > other.cpql_ci_high:
                    shift_percent = int(round(policy.spend_shift_cap_fraction * 100))
                    return _make_decision(
                        estimate=estimate,
                        ad_spend=ad_spend,
                        action=DecisionAction.SHIFT_SPEND,
                        reason=(
                            f"Cost-per-qualified-lead interval for ad '{estimate.advertisement_id}' "
                            f"[₹{estimate.cpql_ci_low:.2f}, ₹{estimate.cpql_ci_high:.2f}] (mean: ₹{estimate.cpql_mean:.2f}) "
                            f"sits entirely above ad '{other.advertisement_id}' interval "
                            f"[₹{other.cpql_ci_low:.2f}, ₹{other.cpql_ci_high:.2f}] (mean: ₹{other.cpql_mean:.2f}). "
                            f"Recommend guardrailed spend shift of up to {shift_percent}% from ad '{estimate.advertisement_id}' "
                            f"to ad '{other.advertisement_id}'."
                        ),
                        policy=policy,
                        now=now,
                        extra_metrics={
                            "relative_rule_triggered": True,
                            "target_ad_id": other.advertisement_id,
                            "target_cpql_mean": other.cpql_mean,
                            "target_cpql_ci": [other.cpql_ci_low, other.cpql_ci_high],
                            "spend_shift_cap_fraction": policy.spend_shift_cap_fraction,
                        },
                    )

    # Rule 8: High CPQL (generic reallocation)
    if (
        not estimate.cpql_unstable
        and estimate.cpql_ci_low is not None
        and estimate.cpql_ci_low > policy.high_cpql_lower_bound
        and estimate.evidence_sufficient_qualification
    ):
        if ad_spend >= policy.budget_guardrail_min_spend:
            is_under_cap = ad_spend <= policy.guardrail_action_spend_cap
            action = DecisionAction.REALLOCATE_BUDGET if is_under_cap else DecisionAction.CONSIDER_REALLOCATE
            action_verb = "Recommending guardrailed spend reallocation (auto-applicable under spend cap)" if is_under_cap else "Recommending spend reallocation for human review"
            return _make_decision(
                estimate=estimate,
                ad_spend=ad_spend,
                action=action,
                reason=(
                    f"Estimated cost per qualified lead has a {ci_pct}% credible interval lower bound of "
                    f"₹{estimate.cpql_ci_low:.2f} (mean: ₹{estimate.cpql_mean:.2f}), exceeding threshold "
                    f"₹{policy.high_cpql_lower_bound:.2f} on spend ₹{ad_spend:.2f} and EQL {estimate.eql_mean:.1f}. "
                    f"{action_verb} (spend: ₹{ad_spend:.2f}, guardrail cap: ₹{policy.guardrail_action_spend_cap:.2f})."
                ),
                policy=policy,
                now=now,
            )

    # Rule 9: High-performing ad with mature evidence and CPQL below target (budget expansion)
    if (
        estimate.evidence_sufficient_reachability
        and estimate.evidence_sufficient_qualification
        and not estimate.cpql_unstable
        and estimate.cpql_ci_high is not None
        and estimate.cpql_ci_high < policy.target_cpql
    ):
        return _make_decision(
            estimate=estimate,
            ad_spend=ad_spend,
            action=DecisionAction.RAISE_BUDGET,
            reason=(
                f"Mature evidence confirmed ({estimate.n_mature_leads} mature leads, {estimate.n_mature_contacts} contacts, "
                f"{estimate.k_qualified} qualified). Credible interval upper bound for CPQL (₹{estimate.cpql_ci_high:.2f}) "
                f"is strictly below target CPQL (₹{policy.target_cpql:.2f}) with mean CPQL ₹{estimate.cpql_mean:.2f}. "
                f"Recommend raising budget (gated tier: human approval required)."
            ),
            policy=policy,
            now=now,
        )

    # Rule 10: Default — continue monitoring
    return _make_decision(
        estimate=estimate,
        ad_spend=ad_spend,
        action=DecisionAction.CONTINUE_MONITORING,
        reason=(
            f"Sample is mature ({estimate.n_mature_leads} mature leads, {estimate.n_mature_contacts} mature contacts, "
            f"{estimate.k_qualified} qualified). Reachability mean {estimate.reachability_mean:.1%} "
            f"({ci_pct}% CI: [{estimate.reachability_ci_low:.1%}, {estimate.reachability_ci_high:.1%}]), "
            f"qualification mean {estimate.qualification_mean:.1%} "
            f"({ci_pct}% CI: [{estimate.qualification_ci_low:.1%}, {estimate.qualification_ci_high:.1%}]), "
            f"EQL {estimate.eql_mean:.1f}, spend ₹{ad_spend:.2f}. No failure threshold triggered; continue autonomous monitoring."
        ),
        policy=policy,
        now=now,
    )


def evaluate_campaign(
    snapshots: list[EstimateSnapshot],
    ad_spends: dict[str, float],
    policy: DecisionPolicy | None = None,
    prior_decisions: list[Decision] | None = None,
) -> list[Decision]:
    """
    Evaluate all ads in a campaign, enabling relative cross-ad rules.

    Args:
        snapshots: EstimateSnapshot objects for all ads in the campaign
        ad_spends: Mapping of ad_id to current ad spend
        policy: Configured DecisionPolicy
        prior_decisions: Prior decisions for cooldown tracking

    Returns:
        List of Decision objects for the campaign ads
    """
    if policy is None:
        policy = DecisionPolicy()

    decisions: list[Decision] = []
    for snap in snapshots:
        spend = ad_spends.get(snap.advertisement_id, 0.0)
        dec = evaluate(
            estimate=snap,
            ad_spend=spend,
            policy=policy,
            prior_decisions=prior_decisions,
            campaign_snapshots=snapshots,
        )
        decisions.append(dec)

    return decisions


def _make_decision(
    estimate: EstimateSnapshot,
    ad_spend: float,
    action: DecisionAction,
    reason: str,
    policy: DecisionPolicy,
    now: datetime,
    extra_metrics: dict | None = None,
) -> Decision:
    """Construct a Decision object storing inputs, posterior summary, thresholds, tier, and auto_applied."""
    tier, auto_applied, requires_approval = _determine_tier_and_auto_applied(
        action=action,
        ad_spend=ad_spend,
        policy=policy,
    )
    approval_status = (
        ApprovalStatus.PENDING if requires_approval else ApprovalStatus.NOT_REQUIRED
    )
    confidence_level = _compute_confidence(estimate)

    inputs = {
        "ad_spend": float(ad_spend),
        "n_leads": estimate.n_leads,
        "n_mature_leads": estimate.n_mature_leads,
        "n_contacts": estimate.n_contacts,
        "n_mature_contacts": estimate.n_mature_contacts,
        "k_qualified": estimate.k_qualified,
        "maturity_fraction_contact": round(estimate.maturity_fraction_contact, 4),
        "maturity_fraction_qualification": round(estimate.maturity_fraction_qualification, 4),
    }

    posterior_summary = {
        "ci_level": round(estimate.ci_level, 4) if getattr(estimate, "ci_level", None) else 0.90,
        "reachability_mean": round(estimate.reachability_mean, 4),
        "reachability_ci": [round(estimate.reachability_ci_low, 4), round(estimate.reachability_ci_high, 4)],
        "qualification_mean": round(estimate.qualification_mean, 4),
        "qualification_ci": [round(estimate.qualification_ci_low, 4), round(estimate.qualification_ci_high, 4)],
        "eql_mean": round(estimate.eql_mean, 2),
        "cpql_mean": round(estimate.cpql_mean, 2) if estimate.cpql_mean is not None else None,
        "cpql_ci": (
            [round(estimate.cpql_ci_low, 2), round(estimate.cpql_ci_high, 2)]
            if (estimate.cpql_ci_low is not None and estimate.cpql_ci_high is not None)
            else None
        ),
        "cpql_unstable": estimate.cpql_unstable,
        "zero_eql_fraction": round(estimate.zero_eql_fraction, 4),
    }

    thresholds = {
        "min_mature_leads": policy.min_mature_leads_for_reachability,
        "min_mature_contacts": policy.min_mature_contacts_for_qualification,
        "min_maturity_fraction": policy.min_maturity_fraction,
        "low_reachability_upper_bound": policy.low_reachability_upper_bound,
        "low_qualification_upper_bound": policy.low_qualification_upper_bound,
        "high_cpql_lower_bound": policy.high_cpql_lower_bound,
        "target_cpql": policy.target_cpql,
        "budget_guardrail_min_spend": policy.budget_guardrail_min_spend,
        "spend_shift_cap_fraction": policy.spend_shift_cap_fraction,
        "guardrail_action_spend_cap": policy.guardrail_action_spend_cap,
    }

    supporting_metrics = {
        "inputs": inputs,
        "posterior_summary": posterior_summary,
        "thresholds": thresholds,
        "tier": tier,
        "auto_applied": auto_applied,
        "policy_version": policy.version,
        # Flat legacy keys for backward compatibility
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
        "cpql_mean": round(estimate.cpql_mean, 2) if estimate.cpql_mean is not None else None,
        "cpql_unstable": estimate.cpql_unstable,
        "evidence_sufficient_reachability": estimate.evidence_sufficient_reachability,
        "evidence_sufficient_qualification": estimate.evidence_sufficient_qualification,
        "ci_level": round(estimate.ci_level, 4) if getattr(estimate, "ci_level", None) else 0.90,
        "thresholds_applied": thresholds,
    }
    if extra_metrics:
        supporting_metrics.update(extra_metrics)

    return Decision(
        advertisement_id=estimate.advertisement_id,
        estimate_snapshot_id=estimate.id,
        policy_version=policy.version,
        action=action,
        reason=reason,
        supporting_metrics=supporting_metrics,
        confidence_level=confidence_level,
        tier=tier,
        auto_applied=auto_applied,
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
        and not estimate.cpql_unstable
    ):
        return "high"
    elif estimate.evidence_sufficient_reachability:
        return "medium"
    else:
        return "low"
