"""
Tests for the decision engine.

Tests verify:
- All 10 rules fire in the correct priority order
- Identical inputs always produce identical outputs (determinism)
- Cooldown period is respected
- Budget guardrail overrides pause recommendations
- Audit evidence is fully recorded in each decision
- Low reachability does NOT trigger a pause recommendation
- Low reachability IS correctly distinguished from low qualification
"""

import pytest
from datetime import datetime, timedelta, timezone

from domain.enums import DecisionAction, ApprovalStatus
from domain.models import EstimateSnapshot, Decision
from decision_engine.engine import DecisionPolicy, evaluate


def _make_snapshot(
    ad_id: str = "ad1",
    n_leads: int = 50,
    n_mature_leads: int = 50,
    k_contacted: int = 35,
    n_contacts: int = 35,
    n_mature_contacts: int = 30,
    k_qualified: int = 10,
    maturity_fraction_contact: float = 1.0,
    maturity_fraction_qualification: float = 1.0,
    reachability_mean: float = 0.70,
    reachability_ci_low: float = 0.56,
    reachability_ci_high: float = 0.82,
    qualification_mean: float = 0.30,
    qualification_ci_low: float = 0.18,
    qualification_ci_high: float = 0.44,
    eql_mean: float = 10.5,
    eql_ci_low: float = 5.0,
    eql_ci_high: float = 17.0,
    cpql_mean: float | None = 476.2,
    cpql_ci_low: float | None = 294.0,
    cpql_ci_high: float | None = 1000.0,
    cpql_unstable: bool = False,
    evidence_sufficient_reachability: bool = True,
    evidence_sufficient_qualification: bool = True,
    zero_eql_fraction: float = 0.02,
    ci_level: float = 0.90,
) -> EstimateSnapshot:
    return EstimateSnapshot(
        advertisement_id=ad_id,
        computed_at=datetime.now(timezone.utc),
        estimator_version="0.1.0",
        n_leads=n_leads,
        n_mature_leads=n_mature_leads,
        n_contacts=n_contacts,
        n_mature_contacts=n_mature_contacts,
        k_qualified=k_qualified,
        maturity_fraction_contact=maturity_fraction_contact,
        maturity_fraction_qualification=maturity_fraction_qualification,
        reachability_mean=reachability_mean,
        reachability_ci_low=reachability_ci_low,
        reachability_ci_high=reachability_ci_high,
        qualification_mean=qualification_mean,
        qualification_ci_low=qualification_ci_low,
        qualification_ci_high=qualification_ci_high,
        eql_mean=eql_mean,
        eql_ci_low=eql_ci_low,
        eql_ci_high=eql_ci_high,
        cpql_mean=cpql_mean,
        cpql_ci_low=cpql_ci_low,
        cpql_ci_high=cpql_ci_high,
        cpql_unstable=cpql_unstable,
        evidence_sufficient_reachability=evidence_sufficient_reachability,
        evidence_sufficient_qualification=evidence_sufficient_qualification,
        zero_eql_fraction=zero_eql_fraction,
        ci_level=ci_level,
    )


class TestRulePriority:
    def test_rule1_insufficient_maturity_fraction(self):
        """Rule 1: Low maturity fraction fires before any other rule."""
        snap = _make_snapshot(
            maturity_fraction_contact=0.30,  # below 0.60 default threshold
            n_mature_leads=5,
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.FLAG_INSUFFICIENT_EVIDENCE

    def test_rule2_insufficient_sample_size(self):
        """Rule 2: Mature but below min_mature_leads threshold."""
        snap = _make_snapshot(
            maturity_fraction_contact=0.80,
            n_mature_leads=15,  # below threshold of 30
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.COLLECT_MORE_DATA

    def test_rule3_insufficient_qualification_sample(self):
        """Rule 3: Reachability data sufficient but qualification data is not."""
        snap = _make_snapshot(
            maturity_fraction_contact=0.90,
            n_mature_leads=50,
            n_mature_contacts=10,  # below threshold of 20
            evidence_sufficient_qualification=False,
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.COLLECT_MORE_DATA

    def test_rule4_anomaly_detection(self):
        """Rule 4: Large qualification rate change triggers anomaly flag."""
        snap = _make_snapshot(qualification_mean=0.05)  # current: 5%
        prior_snap = _make_snapshot(qualification_mean=0.30)  # prior: 30%

        decision = evaluate(snap, ad_spend=5000.0, prior_estimate=prior_snap)
        assert decision.action == DecisionAction.FLAG_ABNORMAL_CHANGE
        assert decision.requires_human_approval is True

    def test_rule5_low_reachability_does_not_trigger_pause(self):
        """Rule 5: Low reachability triggers investigate, NOT pause."""
        snap = _make_snapshot(
            reachability_mean=0.15,
            reachability_ci_low=0.08,
            reachability_ci_high=0.22,  # entire CI below 0.25 threshold
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.INVESTIGATE_LOW_REACHABILITY
        assert decision.action != DecisionAction.CONSIDER_PAUSE

    def test_rule6_low_qualification_triggers_consider_pause(self):
        """Rule 6: Strong evidence of low qualification with sufficient reachability."""
        snap = _make_snapshot(
            reachability_mean=0.65,
            reachability_ci_low=0.50,
            reachability_ci_high=0.78,
            qualification_mean=0.04,
            qualification_ci_low=0.01,
            qualification_ci_high=0.09,  # entire CI below 0.10 threshold
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.CONSIDER_PAUSE
        assert decision.requires_human_approval is True

    def test_rule7_high_cpql_triggers_reallocate(self):
        """Rule 7: CPQL CI lower bound exceeds threshold."""
        snap = _make_snapshot(
            qualification_mean=0.20,
            qualification_ci_low=0.12,
            qualification_ci_high=0.30,
            cpql_mean=750.0,
            cpql_ci_low=600.0,  # above $500 threshold
            cpql_ci_high=1000.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.CONSIDER_REALLOCATE
        assert decision.requires_human_approval is True

    def test_rule_budget_guardrail_overrides_pause(self):
        """Budget guardrail: low qualification but tiny spend → continue monitoring."""
        snap = _make_snapshot(
            reachability_mean=0.65,
            reachability_ci_low=0.50,
            reachability_ci_high=0.78,
            qualification_mean=0.04,
            qualification_ci_low=0.01,
            qualification_ci_high=0.09,
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
        )
        decision = evaluate(snap, ad_spend=50.0)  # below $100 guardrail
        assert decision.action == DecisionAction.CONTINUE_MONITORING

    def test_rule_default_continue_monitoring(self):
        """Rule 10: All rules pass — default to continue monitoring."""
        snap = _make_snapshot()  # default values are all healthy
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.CONTINUE_MONITORING
        assert decision.requires_human_approval is False


class TestDeterminism:
    def test_same_inputs_always_produce_same_action(self):
        snap = _make_snapshot()
        decisions = [evaluate(snap, ad_spend=5000.0) for _ in range(10)]
        actions = {d.action for d in decisions}
        assert len(actions) == 1, "Decision engine must be deterministic"

    def test_different_estimates_produce_different_actions(self):
        good_snap = _make_snapshot(
            qualification_ci_low=0.20,
            qualification_ci_high=0.40,
        )
        bad_snap = _make_snapshot(
            qualification_ci_low=0.01,
            qualification_ci_high=0.09,
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
            reachability_ci_low=0.50,
            reachability_ci_high=0.80,
        )
        good_decision = evaluate(good_snap, ad_spend=5000.0)
        bad_decision = evaluate(bad_snap, ad_spend=5000.0)
        assert good_decision.action != bad_decision.action


class TestCooldown:
    def test_active_cooldown_produces_continue_monitoring(self):
        snap = _make_snapshot(
            qualification_ci_low=0.01,
            qualification_ci_high=0.09,
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
            reachability_ci_low=0.50,
            reachability_ci_high=0.80,
        )
        now = datetime.now(timezone.utc)
        prior_decision = Decision(
            advertisement_id="ad1",
            estimate_snapshot_id="snap1",
            policy_version="v0.1.0",
            action=DecisionAction.CONSIDER_PAUSE,
            reason="prior decision",
            supporting_metrics={},
            confidence_level="high",
            requires_human_approval=True,
            approval_status=ApprovalStatus.PENDING,
            created_at=now - timedelta(hours=10),  # 10 hours ago — inside 48h cooldown
        )
        decision = evaluate(snap, ad_spend=5000.0, prior_decisions=[prior_decision])
        # Should not fire again — cooldown active
        assert decision.action == DecisionAction.CONTINUE_MONITORING

    def test_expired_cooldown_allows_new_decision(self):
        snap = _make_snapshot(
            qualification_ci_low=0.01,
            qualification_ci_high=0.09,
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
            reachability_ci_low=0.50,
            reachability_ci_high=0.80,
        )
        now = datetime.now(timezone.utc)
        prior_decision = Decision(
            advertisement_id="ad1",
            estimate_snapshot_id="snap1",
            policy_version="v0.1.0",
            action=DecisionAction.CONSIDER_PAUSE,
            reason="prior decision",
            supporting_metrics={},
            confidence_level="high",
            requires_human_approval=True,
            approval_status=ApprovalStatus.PENDING,
            created_at=now - timedelta(hours=72),  # 72 hours ago — cooldown expired
        )
        decision = evaluate(snap, ad_spend=5000.0, prior_decisions=[prior_decision])
        # Cooldown expired — should fire the pause recommendation again
        assert decision.action == DecisionAction.CONSIDER_PAUSE


class TestEvidenceRecording:
    def test_decision_records_all_supporting_metrics(self):
        snap = _make_snapshot()
        decision = evaluate(snap, ad_spend=5000.0)
        metrics = decision.supporting_metrics
        required_keys = [
            "n_leads", "n_mature_leads", "n_mature_contacts", "k_qualified",
            "reachability_mean", "qualification_mean", "policy_version",
            "thresholds_applied",
        ]
        for key in required_keys:
            assert key in metrics, f"Supporting metrics missing: {key}"

    def test_decision_records_policy_version(self):
        snap = _make_snapshot()
        policy = DecisionPolicy(version="v0.2.0-test")
        decision = evaluate(snap, ad_spend=5000.0, policy=policy)
        assert decision.policy_version == "v0.2.0-test"

    def test_low_reachability_decision_explicitly_states_not_pause(self):
        """The investigate_low_reachability reason must warn against misinterpreting as pause."""
        snap = _make_snapshot(
            reachability_ci_low=0.08,
            reachability_ci_high=0.22,
        )
        decision = evaluate(snap, ad_spend=5000.0)
        assert decision.action == DecisionAction.INVESTIGATE_LOW_REACHABILITY
        assert "NOT" in decision.reason.upper() or "not" in decision.reason, (
            "Low reachability decision should explicitly warn against misinterpreting as intent failure"
        )


class TestDecisionRecordsAndTiers:
    def test_decision_tier_and_auto_applied_rules(self):
        """Test tier assignment and auto_applied behavior across actions."""
        policy = DecisionPolicy(guardrail_action_spend_cap=500.0)

        # 1. Raising budget and launching must ALWAYS be tier=gated and auto_applied=false
        from decision_engine.engine import _determine_tier_and_auto_applied
        tier_launch, auto_launch, req_launch = _determine_tier_and_auto_applied(
            DecisionAction.LAUNCH_AD, ad_spend=100.0, policy=policy
        )
        assert tier_launch == "gated"
        assert auto_launch is False
        assert req_launch is True

        tier_raise, auto_raise, req_raise = _determine_tier_and_auto_applied(
            DecisionAction.RAISE_BUDGET, ad_spend=100.0, policy=policy
        )
        assert tier_raise == "gated"
        assert auto_raise is False
        assert req_raise is True

        # 2. Pausing within guardrail spend cap (<= 500) -> tier=within_guardrails, auto_applied=True
        pause_snap = _make_snapshot(
            qualification_ci_low=0.01,
            qualification_ci_high=0.08,
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
            reachability_ci_low=0.50,
            reachability_ci_high=0.80,
        )
        dec_under_cap = evaluate(pause_snap, ad_spend=300.0, policy=policy)
        assert dec_under_cap.action == DecisionAction.PAUSE_AD
        assert dec_under_cap.tier == "within_guardrails"
        assert dec_under_cap.auto_applied is True
        assert dec_under_cap.requires_human_approval is False

        # 3. Pausing above guardrail spend cap (> 500) -> tier=within_guardrails, auto_applied=False (recommendation)
        dec_over_cap = evaluate(pause_snap, ad_spend=800.0, policy=policy)
        assert dec_over_cap.action == DecisionAction.CONSIDER_PAUSE
        assert dec_over_cap.tier == "within_guardrails"
        assert dec_over_cap.auto_applied is False
        assert dec_over_cap.requires_human_approval is True

        # 4. Observational / monitoring -> tier=autonomous, auto_applied=True
        normal_snap = _make_snapshot(
            qualification_ci_low=0.20,
            qualification_ci_high=0.40,
            reachability_ci_low=0.60,
            reachability_ci_high=0.80,
        )
        dec_auto = evaluate(normal_snap, ad_spend=100.0, policy=policy)
        assert dec_auto.action == DecisionAction.CONTINUE_MONITORING
        assert dec_auto.tier == "autonomous"
        assert dec_auto.auto_applied is True

    def test_relative_rule_cost_per_qualified_lead_shift(self):
        """If one ad's CPQL interval sits entirely above another's in the same campaign, emit spend shift."""
        # Ad A: High CPQL interval [800.0, 1200.0]
        ad_a = _make_snapshot(
            ad_id="ad_high_cost",
            cpql_mean=1000.0,
            cpql_ci_low=800.0,
            cpql_ci_high=1200.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
            qualification_ci_low=0.15,
            qualification_ci_high=0.25,
            reachability_ci_low=0.50,
            reachability_ci_high=0.70,
        )
        # Ad B: Low CPQL interval [100.0, 300.0]
        ad_b = _make_snapshot(
            ad_id="ad_efficient",
            cpql_mean=200.0,
            cpql_ci_low=100.0,
            cpql_ci_high=300.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
            qualification_ci_low=0.30,
            qualification_ci_high=0.45,
            reachability_ci_low=0.70,
            reachability_ci_high=0.85,
        )

        policy = DecisionPolicy(spend_shift_cap_fraction=0.30, guardrail_action_spend_cap=1000.0)
        dec_a = evaluate(
            estimate=ad_a,
            ad_spend=600.0,
            policy=policy,
            campaign_snapshots=[ad_a, ad_b],
        )

        assert dec_a.action == DecisionAction.SHIFT_SPEND
        assert dec_a.tier == "within_guardrails"
        assert "ad_efficient" in dec_a.reason
        assert "800.00" in dec_a.reason
        assert "300.00" in dec_a.reason
        assert "30%" in dec_a.reason
        assert dec_a.supporting_metrics.get("relative_rule_triggered") is True
        assert dec_a.supporting_metrics.get("target_ad_id") == "ad_efficient"

    def test_evaluate_campaign_relative_spend_shift(self):
        """Campaign-level evaluation triggers spend shift from inefficient ad to efficient ad."""
        from decision_engine.engine import evaluate_campaign
        ad_expensive = _make_snapshot(
            ad_id="ad_exp",
            cpql_mean=900.0,
            cpql_ci_low=750.0,
            cpql_ci_high=1100.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
            qualification_ci_low=0.15,
            qualification_ci_high=0.25,
            reachability_ci_low=0.50,
            reachability_ci_high=0.70,
        )
        ad_cheap = _make_snapshot(
            ad_id="ad_chp",
            cpql_mean=180.0,
            cpql_ci_low=120.0,
            cpql_ci_high=240.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
            qualification_ci_low=0.35,
            qualification_ci_high=0.50,
            reachability_ci_low=0.75,
            reachability_ci_high=0.90,
        )
        policy = DecisionPolicy(spend_shift_cap_fraction=0.25, guardrail_action_spend_cap=2000.0)
        ad_spends = {"ad_exp": 1200.0, "ad_chp": 1200.0}

        decisions = evaluate_campaign(
            snapshots=[ad_expensive, ad_cheap],
            ad_spends=ad_spends,
            policy=policy,
        )
        dec_exp = next(d for d in decisions if d.advertisement_id == "ad_exp")
        assert dec_exp.action == DecisionAction.SHIFT_SPEND
        assert dec_exp.tier == "within_guardrails"
        assert dec_exp.auto_applied is True
        assert dec_exp.supporting_metrics["target_ad_id"] == "ad_chp"
        assert "25%" in dec_exp.reason

    def test_relative_spend_shift_respects_budget_guardrail_min_spend(self):
        """Relative spend shift must not fire if ad spend is below budget_guardrail_min_spend."""
        ad_expensive = _make_snapshot(
            ad_id="ad_exp_low_spend",
            cpql_mean=900.0,
            cpql_ci_low=750.0,
            cpql_ci_high=1100.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
            reachability_ci_low=0.50,
            reachability_ci_high=0.70,
        )
        ad_cheap = _make_snapshot(
            ad_id="ad_chp_target",
            cpql_mean=180.0,
            cpql_ci_low=120.0,
            cpql_ci_high=240.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
            reachability_ci_low=0.75,
            reachability_ci_high=0.90,
        )
        policy = DecisionPolicy(budget_guardrail_min_spend=100.0)

        # Spend is $50 (< $100 min guardrail)
        dec_under = evaluate(
            estimate=ad_expensive,
            ad_spend=50.0,
            policy=policy,
            campaign_snapshots=[ad_expensive, ad_cheap],
        )
        # Should not recommend spend shift when below min spend guardrail
        assert dec_under.action != DecisionAction.SHIFT_SPEND
        assert dec_under.action == DecisionAction.CONTINUE_MONITORING

        # Spend is $150 (>= $100 min guardrail)
        dec_over = evaluate(
            estimate=ad_expensive,
            ad_spend=150.0,
            policy=policy,
            campaign_snapshots=[ad_expensive, ad_cheap],
        )
        assert dec_over.action == DecisionAction.SHIFT_SPEND

    def test_decision_record_stores_required_structured_fields(self):
        """Every decision must store inputs, posterior summary, thresholds, tier, auto_applied, policy version."""
        snap = _make_snapshot(
            cpql_mean=250.0,
            cpql_ci_low=200.0,
            cpql_ci_high=320.0,
        )
        policy = DecisionPolicy(version="v0.2.0-custom")
        decision = evaluate(snap, ad_spend=450.0, policy=policy)

        metrics = decision.supporting_metrics
        assert "inputs" in metrics
        assert "posterior_summary" in metrics
        assert "thresholds" in metrics
        assert "tier" in metrics
        assert "auto_applied" in metrics
        assert "policy_version" in metrics

        # Verify inputs content
        assert metrics["inputs"]["ad_spend"] == 450.0
        assert metrics["inputs"]["n_leads"] == snap.n_leads

        # Verify posterior summary content
        assert metrics["posterior_summary"]["reachability_mean"] == round(snap.reachability_mean, 4)
        assert metrics["posterior_summary"]["cpql_mean"] == 250.0

        # Verify thresholds content
        assert metrics["thresholds"]["min_maturity_fraction"] == policy.min_maturity_fraction

        # Verify plain-language reason is derived from actual numbers
        assert str(snap.n_mature_leads) in decision.reason
        assert f"{snap.reachability_mean:.1%}" in decision.reason

    def test_reallocation_under_and_over_guardrail_cap(self):
        """Reallocation under cap emits REALLOCATE_BUDGET (auto_applied=True); over cap emits CONSIDER_REALLOCATE."""
        snap = _make_snapshot(
            qualification_mean=0.20,
            qualification_ci_low=0.12,
            qualification_ci_high=0.30,
            cpql_mean=750.0,
            cpql_ci_low=600.0,
            cpql_ci_high=1000.0,
            cpql_unstable=False,
            evidence_sufficient_qualification=True,
        )
        policy = DecisionPolicy(guardrail_action_spend_cap=500.0, budget_guardrail_min_spend=100.0)

        # Under cap: auto-applied reallocate
        dec_under = evaluate(snap, ad_spend=400.0, policy=policy)
        assert dec_under.action == DecisionAction.REALLOCATE_BUDGET
        assert dec_under.auto_applied is True
        assert dec_under.requires_human_approval is False

        # Over cap: recommendation for human review
        dec_over = evaluate(snap, ad_spend=750.0, policy=policy)
        assert dec_over.action == DecisionAction.CONSIDER_REALLOCATE
        assert dec_over.auto_applied is False
        assert dec_over.requires_human_approval is True

    def test_confidence_clamped_when_cpql_unstable(self):
        """A decision must never be labeled 'high' confidence when cpql_unstable is True."""
        snap = _make_snapshot(
            evidence_sufficient_reachability=True,
            evidence_sufficient_qualification=True,
            cpql_unstable=True,
        )
        decision = evaluate(snap, ad_spend=200.0)
        assert decision.confidence_level != "high"
        assert decision.confidence_level in ("medium", "low")

    def test_single_spend_shift_cap_used_consistently(self):
        """The spend-shift cap configured value must be the single parameter used everywhere."""
        policy = DecisionPolicy(spend_shift_cap_fraction=0.35)
        snap = _make_snapshot()
        decision = evaluate(snap, ad_spend=200.0, policy=policy)
        assert decision.supporting_metrics["thresholds"]["spend_shift_cap_fraction"] == 0.35

    def test_naturally_emits_raise_budget_for_mature_ad_below_target_cpql(self):
        """Engine naturally emits RAISE_BUDGET (tier=gated, auto_applied=false) when CPQL CI high < target_cpql."""
        snap = _make_snapshot(
            reachability_mean=0.75,
            reachability_ci_low=0.60,
            reachability_ci_high=0.88,
            qualification_mean=0.45,
            qualification_ci_low=0.35,
            qualification_ci_high=0.55,
            cpql_mean=45.0,
            cpql_ci_low=32.0,
            cpql_ci_high=58.0,  # Below target_cpql of 75.0
            cpql_unstable=False,
            evidence_sufficient_reachability=True,
            evidence_sufficient_qualification=True,
            n_mature_leads=40,
            n_mature_contacts=30,
            k_qualified=14,
        )
        policy = DecisionPolicy(target_cpql=75.0)
        decision = evaluate(snap, ad_spend=600.0, policy=policy)

        assert decision.action == DecisionAction.RAISE_BUDGET
        assert decision.tier == "gated"
        assert decision.auto_applied is False
        assert decision.requires_human_approval is True
        assert decision.approval_status == ApprovalStatus.PENDING
        assert "target CPQL" in decision.reason
        assert "₹58.00" in decision.reason


class TestDecisionSemanticsAndSnapshotIntegrity:
    """Regression tests for decision execution semantics and evidence snapshot integrity."""

    def test_advisory_wording_for_guardrail_actions(self):
        """Verify action reason uses advisory wording rather than claiming external campaign mutation."""
        # Low qualification with spend under cap ($400 <= $1000)
        snap = _make_snapshot(
            reachability_mean=0.70,
            reachability_ci_low=0.55,
            reachability_ci_high=0.85,
            qualification_mean=0.03,
            qualification_ci_low=0.01,
            qualification_ci_high=0.07,  # Entire CI < 0.10
            n_mature_contacts=30,
            evidence_sufficient_qualification=True,
        )
        policy = DecisionPolicy(guardrail_action_spend_cap=1000.0)
        decision = evaluate(snap, ad_spend=400.0, policy=policy)

        assert decision.action == DecisionAction.PAUSE_AD
        assert decision.tier == "within_guardrails"
        assert decision.auto_applied is True
        # Advisory wording check
        assert "Recommending guardrailed pause" in decision.reason
        assert not decision.reason.startswith("Pausing ad")

    def test_reallocate_advisory_wording(self):
        """Verify spend reallocation uses advisory phrasing."""
        snap = _make_snapshot(
            qualification_mean=0.25,
            qualification_ci_low=0.15,
            qualification_ci_high=0.35,
            cpql_mean=250.0,
            cpql_ci_low=160.0,
            cpql_ci_high=400.0,
            cpql_unstable=False,
            evidence_sufficient_reachability=True,
            evidence_sufficient_qualification=True,
        )
        policy = DecisionPolicy(
            high_cpql_lower_bound=150.0,
            budget_guardrail_min_spend=500.0,
            guardrail_action_spend_cap=2000.0,
        )
        decision = evaluate(snap, ad_spend=1200.0, policy=policy)

        assert decision.action == DecisionAction.REALLOCATE_BUDGET
        assert decision.tier == "within_guardrails"
        assert decision.auto_applied is True
        assert "Recommending guardrailed spend reallocation" in decision.reason
        assert not decision.reason.startswith("Reallocating spend")

    def test_evidence_snapshot_assembly_and_metrics_integrity(self):
        """Verify supporting_metrics, thresholds, policy_version, and inputs agree with snapshot."""
        snap = _make_snapshot(
            ad_id="ad-audit-test",
            n_leads=60,
            n_mature_leads=50,
            n_contacts=40,
            n_mature_contacts=35,
            k_qualified=12,
            maturity_fraction_contact=0.8333,
            maturity_fraction_qualification=0.8750,
            reachability_mean=0.6854,
            reachability_ci_low=0.5512,
            reachability_ci_high=0.8196,
            qualification_mean=0.3214,
            qualification_ci_low=0.1987,
            qualification_ci_high=0.4561,
            eql_mean=14.25,
            cpql_mean=210.53,
            cpql_ci_low=145.22,
            cpql_ci_high=330.11,
            cpql_unstable=False,
            zero_eql_fraction=0.0150,
        )
        policy = DecisionPolicy()
        spend = 3000.0
        decision = evaluate(snap, ad_spend=spend, policy=policy)

        # Integrity of reference IDs and policy metadata
        assert decision.estimate_snapshot_id == snap.id
        assert decision.policy_version == policy.version

        # Integrity of inputs
        inputs = decision.supporting_metrics["inputs"]
        assert inputs["ad_spend"] == 3000.0
        assert inputs["n_leads"] == 60
        assert inputs["n_mature_leads"] == 50
        assert inputs["n_contacts"] == 40
        assert inputs["n_mature_contacts"] == 35
        assert inputs["k_qualified"] == 12
        assert inputs["maturity_fraction_contact"] == 0.8333
        assert inputs["maturity_fraction_qualification"] == 0.8750

        # Integrity of posterior summary
        posterior = decision.supporting_metrics["posterior_summary"]
        assert posterior["reachability_mean"] == round(snap.reachability_mean, 4)
        assert posterior["reachability_ci"] == [round(snap.reachability_ci_low, 4), round(snap.reachability_ci_high, 4)]
        assert posterior["qualification_mean"] == round(snap.qualification_mean, 4)
        assert posterior["qualification_ci"] == [round(snap.qualification_ci_low, 4), round(snap.qualification_ci_high, 4)]
        assert posterior["eql_mean"] == round(snap.eql_mean, 2)
        assert posterior["cpql_mean"] == round(snap.cpql_mean, 2)
        assert posterior["cpql_ci"] == [round(snap.cpql_ci_low, 2), round(snap.cpql_ci_high, 2)]
        assert posterior["cpql_unstable"] == snap.cpql_unstable
        assert posterior["zero_eql_fraction"] == round(snap.zero_eql_fraction, 4)

        # Integrity of thresholds
        thresholds = decision.supporting_metrics["thresholds"]
        assert thresholds["min_mature_leads"] == policy.min_mature_leads_for_reachability
        assert thresholds["min_mature_contacts"] == policy.min_mature_contacts_for_qualification
        assert thresholds["min_maturity_fraction"] == policy.min_maturity_fraction
        assert thresholds["low_reachability_upper_bound"] == policy.low_reachability_upper_bound
        assert thresholds["low_qualification_upper_bound"] == policy.low_qualification_upper_bound
        assert thresholds["high_cpql_lower_bound"] == policy.high_cpql_lower_bound
        assert thresholds["target_cpql"] == policy.target_cpql
        assert thresholds["budget_guardrail_min_spend"] == policy.budget_guardrail_min_spend
        assert thresholds["spend_shift_cap_fraction"] == policy.spend_shift_cap_fraction
        assert thresholds["guardrail_action_spend_cap"] == policy.guardrail_action_spend_cap

    def test_repeated_evaluation_stability(self):
        """Verify repeated evaluation produces authoritative and deterministic results."""
        snap = _make_snapshot(ad_id="ad-stable-test")
        policy = DecisionPolicy()
        spend = 1500.0

        d1 = evaluate(snap, ad_spend=spend, policy=policy)
        d2 = evaluate(snap, ad_spend=spend, policy=policy)

        assert d1.action == d2.action
        assert d1.tier == d2.tier
        assert d1.auto_applied == d2.auto_applied
        assert d1.confidence_level == d2.confidence_level
        assert d1.reason == d2.reason
        assert d1.supporting_metrics["inputs"] == d2.supporting_metrics["inputs"]
        assert d1.supporting_metrics["posterior_summary"] == d2.supporting_metrics["posterior_summary"]
        assert d1.supporting_metrics["thresholds"] == d2.supporting_metrics["thresholds"]

    def test_credible_interval_reason_text_matches_configured_ci_level(self):
        """Verify displayed credible-interval percentage in reason text accurately reflects ci_level (0.80 vs 0.90)."""
        policy = DecisionPolicy(low_qualification_upper_bound=0.15, low_reachability_upper_bound=0.25)

        # 1. Qualification Pause under 80% CI vs 90% CI
        snap_80 = _make_snapshot(
            ci_level=0.80,
            n_mature_contacts=25,
            k_qualified=1,
            qualification_mean=0.06,
            qualification_ci_low=0.015,
            qualification_ci_high=0.12,  # < 0.15 threshold
            evidence_sufficient_qualification=True,
            reachability_mean=0.60,
            reachability_ci_low=0.45,
            reachability_ci_high=0.75,
        )
        d_80 = evaluate(snap_80, ad_spend=400.0, policy=policy)
        assert d_80.action == DecisionAction.PAUSE_AD
        assert "80% credible interval for qualification rate" in d_80.reason
        assert d_80.supporting_metrics["posterior_summary"]["ci_level"] == 0.80

        snap_90 = _make_snapshot(
            ci_level=0.90,
            n_mature_contacts=25,
            k_qualified=1,
            qualification_mean=0.06,
            qualification_ci_low=0.010,
            qualification_ci_high=0.14,  # < 0.15 threshold
            evidence_sufficient_qualification=True,
            reachability_mean=0.60,
            reachability_ci_low=0.45,
            reachability_ci_high=0.75,
        )
        d_90 = evaluate(snap_90, ad_spend=400.0, policy=policy)
        assert d_90.action == DecisionAction.PAUSE_AD
        assert "90% credible interval for qualification rate" in d_90.reason
        assert d_90.supporting_metrics["posterior_summary"]["ci_level"] == 0.90

        # 2. Low Reachability under 80% vs 90% CI
        reach_snap_80 = _make_snapshot(
            ci_level=0.80,
            reachability_mean=0.15,
            reachability_ci_low=0.05,
            reachability_ci_high=0.22,  # < 0.25
        )
        reach_d_80 = evaluate(reach_snap_80, ad_spend=400.0, policy=policy)
        assert reach_d_80.action == DecisionAction.INVESTIGATE_LOW_REACHABILITY
        assert "The 80% credible interval for reachability" in reach_d_80.reason

        reach_snap_90 = _make_snapshot(
            ci_level=0.90,
            reachability_mean=0.15,
            reachability_ci_low=0.04,
            reachability_ci_high=0.24,  # < 0.25
        )
        reach_d_90 = evaluate(reach_snap_90, ad_spend=400.0, policy=policy)
        assert reach_d_90.action == DecisionAction.INVESTIGATE_LOW_REACHABILITY
        assert "The 90% credible interval for reachability" in reach_d_90.reason

        # 3. Continue Monitoring under 80% vs 90% CI
        cont_snap_80 = _make_snapshot(
            ci_level=0.80,
            evidence_sufficient_reachability=True,
            evidence_sufficient_qualification=True,
            reachability_mean=0.65,
            reachability_ci_low=0.50,
            reachability_ci_high=0.80,
            qualification_mean=0.25,
            qualification_ci_low=0.18,
            qualification_ci_high=0.32,
            cpql_mean=60.0,
            cpql_ci_low=45.0,
            cpql_ci_high=78.0,
            cpql_unstable=False,
        )
        cont_d_80 = evaluate(cont_snap_80, ad_spend=400.0, policy=policy)
        assert cont_d_80.action == DecisionAction.CONTINUE_MONITORING
        assert "(80% CI: [50.0%, 80.0%])" in cont_d_80.reason
        assert "(80% CI: [18.0%, 32.0%])" in cont_d_80.reason

    def test_estimator_and_policy_contact_thresholds_distinct_semantics(self):
        """
        Verify distinct semantics of EstimatorConfig.min_mature_contacts vs
        DecisionPolicy.min_mature_contacts_for_qualification under intermediate contact counts:
        - When N=15:
          * Config A (Est=12, Pol=12): Rule 3 passes, evidence sufficient -> Rule 6 fires (PAUSE)
          * Config B (Est=20, Pol=12): Rule 3 passes, but evidence insufficient -> Rule 6 blocked -> falls through to Rule 10 (CONTINUE_MONITORING)
          * Config C (Est=12, Pol=20): Rule 3 fires directly -> COLLECT_MORE_DATA
          * Config D (Est=20, Pol=20): Rule 3 fires directly -> COLLECT_MORE_DATA
        """
        base_kwargs = dict(
            n_mature_leads=50,
            n_mature_contacts=15,
            k_qualified=1,
            reachability_mean=0.65,
            reachability_ci_low=0.50,
            reachability_ci_high=0.80,
            qualification_mean=0.04,
            qualification_ci_low=0.01,
            qualification_ci_high=0.08,
        )

        # Config A (Est=12, Pol=12)
        snap_a = _make_snapshot(**base_kwargs, evidence_sufficient_qualification=True)
        pol_a = DecisionPolicy(min_mature_contacts_for_qualification=12, low_qualification_upper_bound=0.10)
        dec_a = evaluate(snap_a, ad_spend=400.0, policy=pol_a)
        assert dec_a.action == DecisionAction.PAUSE_AD

        # Config B (Est=20, Pol=12)
        snap_b = _make_snapshot(**base_kwargs, evidence_sufficient_qualification=False)
        pol_b = DecisionPolicy(min_mature_contacts_for_qualification=12, low_qualification_upper_bound=0.10)
        dec_b = evaluate(snap_b, ad_spend=400.0, policy=pol_b)
        assert dec_b.action == DecisionAction.CONTINUE_MONITORING
        assert "Sample is mature" in dec_b.reason

        # Config C (Est=12, Pol=20)
        snap_c = _make_snapshot(**base_kwargs, evidence_sufficient_qualification=True)
        pol_c = DecisionPolicy(min_mature_contacts_for_qualification=20, low_qualification_upper_bound=0.10)
        dec_c = evaluate(snap_c, ad_spend=400.0, policy=pol_c)
        assert dec_c.action == DecisionAction.COLLECT_MORE_DATA
        assert "below required threshold of 20" in dec_c.reason

        # Config D (Est=20, Pol=20)
        snap_d = _make_snapshot(**base_kwargs, evidence_sufficient_qualification=False)
        pol_d = DecisionPolicy(min_mature_contacts_for_qualification=20, low_qualification_upper_bound=0.10)
        dec_d = evaluate(snap_d, ad_spend=400.0, policy=pol_d)
        assert dec_d.action == DecisionAction.COLLECT_MORE_DATA
        assert "below required threshold of 20" in dec_d.reason




