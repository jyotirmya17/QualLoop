"""
Tests for benchmark module (baseline policy and benchmark runner).
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

from benchmark.baseline import BaselinePolicy
from benchmark.runner import BenchmarkRunner, _wilson_score_interval
from domain.enums import CallOutcome, DecisionAction, LeadStatus, QualificationResult
from domain.models import Advertisement, CallAttempt, Lead, QualificationOutcome


def test_wilson_score_interval():
    ci = _wilson_score_interval(10, 100)
    assert 0.0 <= ci[0] <= 0.1 <= ci[1] <= 1.0
    zero_ci = _wilson_score_interval(0, 0)
    assert zero_ci == [0.0, 0.0]


def test_baseline_policy_no_leads():
    policy = BaselinePolicy()
    ad = Advertisement(
        id="ad-1", ad_set_id="as-1", creative_id="cr-1", spend=50.0, impressions=1000, clicks=50
    )
    decision = policy.evaluate(ad, [], [], [])
    assert decision.action == DecisionAction.CONTINUE_MONITORING
    assert decision.n_leads == 0


def test_baseline_policy_low_qualification_pauses():
    policy = BaselinePolicy(pause_threshold=0.10)
    ad = Advertisement(
        id="ad-1", ad_set_id="as-1", creative_id="cr-1", spend=100.0, impressions=2000, clicks=100
    )
    now = datetime.now(timezone.utc)
    leads = [Lead(id=f"lead-{i}", advertisement_id="ad-1", created_at=now) for i in range(20)]
    calls = [
        CallAttempt(id=f"ca-{i}", lead_id=f"lead-{i}", attempted_at=now, outcome=CallOutcome.ANSWERED)
        for i in range(20)
    ]
    # Only 1 out of 20 qualified (5% < 10%)
    quals = [
        QualificationOutcome(id="qo-0", lead_id="lead-0", resolved_at=now, result=QualificationResult.QUALIFIED)
    ] + [
        QualificationOutcome(id=f"qo-{i}", lead_id=f"lead-{i}", resolved_at=now, result=QualificationResult.DISQUALIFIED)
        for i in range(1, 20)
    ]

    decision = policy.evaluate(ad, leads, calls, quals)
    assert decision.action == DecisionAction.CONSIDER_PAUSE
    assert decision.observed_qualification == 0.05
    assert "below threshold" in decision.reason


def test_baseline_policy_high_qualification_continues():
    policy = BaselinePolicy(pause_threshold=0.10)
    ad = Advertisement(
        id="ad-1", ad_set_id="as-1", creative_id="cr-1", spend=100.0, impressions=2000, clicks=100
    )
    now = datetime.now(timezone.utc)
    leads = [Lead(id=f"lead-{i}", advertisement_id="ad-1", created_at=now) for i in range(10)]
    calls = [
        CallAttempt(id=f"ca-{i}", lead_id=f"lead-{i}", attempted_at=now, outcome=CallOutcome.ANSWERED)
        for i in range(10)
    ]
    # 3 out of 10 qualified (30% >= 10%)
    quals = [
        QualificationOutcome(id=f"qo-{i}", lead_id=f"lead-{i}", resolved_at=now, result=QualificationResult.QUALIFIED)
        for i in range(3)
    ]

    decision = policy.evaluate(ad, leads, calls, quals)
    assert decision.action == DecisionAction.CONTINUE_MONITORING
    assert decision.observed_qualification == 0.30


def test_benchmark_runner_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir) / "results"
        runner = BenchmarkRunner(results_dir=results_dir)

        # Run with max 1 simulation per scenario for quick test verification
        report = runner.run_benchmark(max_runs_per_scenario=1)

        assert report.run_metadata["n_simulations"] == 9  # 9 scenario presets
        assert report.run_metadata["n_ads_evaluated"] > 0
        assert "qualloop" in report.aggregate_metrics
        assert "baseline" in report.aggregate_metrics

        # Ensure files were written
        assert (results_dir / "REPORT.md").exists()
        assert (results_dir / "latest_benchmark.json").exists()

        # Check content of REPORT.md
        content = (results_dir / "REPORT.md").read_text(encoding="utf-8")
        assert "QualLoop vs. Naive Baseline Benchmark Report" in content
        assert "False Positive Pause Rate (FPPR)" in content


def test_time_sliced_benchmark_runner():
    from benchmark.time_sliced import TimeSlicedBenchmarkRunner

    runner = TimeSlicedBenchmarkRunner(checkpoints=(3, 7, 14, 21))
    summary = runner.run(max_runs_per_scenario=1)

    assert summary.n_simulations == 9
    assert summary.n_poor_ads > 0
    assert "day_3" in summary.qualloop_distribution
    assert "day_7" in summary.qualloop_distribution
    assert "day_14" in summary.qualloop_distribution
    assert "day_21" in summary.qualloop_distribution
    assert "missed" in summary.qualloop_distribution
    assert summary.qualloop_missed_count >= 0
    assert 0.0 <= summary.qualloop_missed_rate <= 1.0


def test_runner_modes_emit_reconciled_counts():
    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = Path(tmpdir) / "results"
        runner = BenchmarkRunner(results_dir=results_dir)

        # Test full mode metadata
        full_rep = runner.run_full(max_runs_per_scenario=1)
        meta = full_rep.run_metadata
        for key in ("mode", "n_simulations", "n_scenarios", "seeds_file_used", "n_ads", "n_good", "n_poor"):
            assert key in meta, f"Missing key in full run_metadata: {key}"
        assert meta["mode"] == "full"
        assert meta["n_simulations"] == 9

        # Test holdout mode metadata
        holdout_rep = runner.run_holdout(max_runs_per_scenario=1)
        meta_h = holdout_rep.run_metadata
        assert meta_h["mode"] == "holdout"
        assert "holdout" in meta_h["seeds_file_used"]

        # Test ablation mode metadata
        abl = runner.run_ablation(max_runs_per_scenario=1)
        meta_a = abl["run_metadata"]
        assert meta_a["mode"] == "ablation"
        for key in ("n_simulations", "n_scenarios", "seeds_file_used", "n_ads", "n_good", "n_poor"):
            assert key in meta_a, f"Missing key in ablation run_metadata: {key}"


def test_sequential_closed_loop_runner():
    from benchmark.sequential import SequentialClosedLoopRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = SequentialClosedLoopRunner(results_dir=Path(tmpdir))
        res = runner.run_benchmark(max_runs_per_scenario=1, save_filename="temp_seq.json")

        meta = res["run_metadata"]
        assert meta["experiment"] == "sequential_closed_loop_simulation"
        assert meta["n_simulations"] == 9
        assert meta["n_scenarios"] == 9
        assert meta["n_ads"] > 0
        assert meta["n_poor"] > 0

        policies = res["policies"]
        assert "oracle" in policies
        assert "qualloop" in policies
        assert "baseline_b" in policies
        assert "baseline_a" in policies
        assert "baseline_c" in policies

        oracle = policies["oracle"]
        assert oracle["spend_on_poor_ads"] == 0.0
        assert oracle["qualified_leads_forgone_from_good_ads"] == 0
        assert oracle["efficiency_vs_oracle"] == 1.0

        qualloop = policies["qualloop"]
        assert qualloop["cumulative_spend"] > 0.0
        assert qualloop["ql_per_rupee"] > 0.0


def test_holdout_sequential_evaluation():
    from benchmark.evaluate_holdout import wilson_score_interval

    # Test Wilson confidence interval calculation
    low, high = wilson_score_interval(10, 100, 0.95)
    assert 0.05 < low < 0.10
    assert 0.10 < high < 0.18

    # Verify saved holdout benchmark json
    holdout_file = Path(__file__).resolve().parent.parent / "benchmark" / "results" / "holdout_sequential.json"
    if holdout_file.exists():
        with open(holdout_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["metadata"]["split_evaluated"] == "holdout"
        assert data["metadata"]["n_simulations"] == 100
        assert data["metadata"]["n_ads"] == 175
        assert "qualloop" in data["policy_metrics"]
        assert "baseline_b" in data["policy_metrics"]
        assert "baseline_a" in data["policy_metrics"]
        assert "paired_tests" in data
        assert "scenario_breakdown" in data


def test_continuous_robustness_benchmark():
    from benchmark.robustness import generate_continuous_scenario, run_continuous_robustness_benchmark

    sc = generate_continuous_scenario(seed=9999, n_ads=2)
    assert len(sc.ads_per_campaign[0]) == 2
    assert 0.02 <= sc.ads_per_campaign[0][0].true_intent <= 0.40

    rob_file = Path(__file__).resolve().parent.parent / "benchmark" / "results" / "robustness_benchmark.json"
    if rob_file.exists():
        with open(rob_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["metadata"]["experiment"] == "continuous_intent_robustness_benchmark"
        assert "qualloop" in data["policy_summaries"]
        assert "strata_analysis" in data


def test_paired_test_sign_convention():
    """Verify that paired test difference is explicitly defined as QualLoop minus Opponent."""
    import numpy as np
    from scipy import stats

    ql = np.array([0.004, 0.005, 0.006])
    opp = np.array([0.003, 0.003, 0.003])
    diff = ql - opp  # QualLoop minus Opponent
    assert np.all(diff > 0)
    t_res = stats.ttest_rel(ql, opp)
    assert t_res.statistic > 0, "Positive statistic indicates QualLoop is higher"

    # Verify holdout results schema and sign convention
    holdout_file = Path(__file__).resolve().parent.parent / "benchmark" / "results" / "holdout_sequential.json"
    if holdout_file.exists():
        with open(holdout_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "qualloop_vs_baseline_a" in data.get("paired_tests", {}):
            pt = data["paired_tests"]["qualloop_vs_baseline_a"]
            assert "sign_convention" in pt
            assert "qualloop_minus_baseline_a" in pt["sign_convention"]
            ql_m = pt["ql_per_rupee"]
            assert "qualloop_pooled_ratio" in ql_m
            assert "opponent_pooled_ratio" in ql_m
            assert "qualloop_mean_per_run_ratio" in ql_m
            assert "opponent_mean_per_run_ratio" in ql_m
            # Mean diff should equal QualLoop mean minus Opponent mean
            expected_diff = round(ql_m["qualloop_mean_per_run_ratio"] - ql_m["opponent_mean_per_run_ratio"], 6)
            assert abs(ql_m["mean_diff"] - expected_diff) < 1e-5


def test_spend_accounting_audit():
    """Verify that the ₹122,142.84 difference in Baseline A good ad spend is accounted for exactly."""
    from benchmark.diagnose_spend import audit_good_ad_spend_gap

    audit = audit_good_ad_spend_gap()
    assert audit["n_paused_good_ads"] == 7
    for paused_ad in audit["paused_ads_breakdown"]:
        assert paused_ad["scenario"] == "high_cpql"
        assert paused_ad["full_spend"] == 20000.0
    assert abs(audit["actual_difference"] - audit["total_forgone_explained"]) < 0.01


def test_baseline_c_policy():
    from benchmark.baseline import BaselineCPolicy

    policy = BaselineCPolicy(pause_threshold=0.15, min_contacts=12, qualification_maturity_days=7.0)
    ad = Advertisement(id="ad-c-1", ad_set_id="as-1", creative_id="cr-c-1", spend=5000.0, impressions=10000, clicks=500)

    now = datetime(2025, 1, 20, 0, 0, tzinfo=timezone.utc)

    # 1. Immature leads created 3 days ago should be excluded
    immature_leads = [
        Lead(id=f"lead-imm-{i}", advertisement_id=ad.id, created_at=now - timedelta(days=3), status=LeadStatus.SUBMITTED)
        for i in range(20)
    ]
    dec = policy.evaluate(advertisement=ad, leads=immature_leads, call_attempts=[], qualification_outcomes=[], observation_time=now)
    assert dec.action == DecisionAction.CONTINUE_MONITORING
    assert dec.n_leads == 0  # 0 mature leads

    # 2. Mature leads created 10 days ago, 15 contacts, but only 1 qualified (1/15 = 6.7% < 15%) -> PAUSE
    mature_leads = [
        Lead(id=f"lead-mat-{i}", advertisement_id=ad.id, created_at=now - timedelta(days=10), status=LeadStatus.SUBMITTED)
        for i in range(20)
    ]
    calls = [
        CallAttempt(id=f"ca-{i}", lead_id=f"lead-mat-{i}", attempted_at=now - timedelta(days=9), outcome=CallOutcome.ANSWERED)
        for i in range(15)
    ]
    quals = [
        QualificationOutcome(id="qo-1", lead_id="lead-mat-0", resolved_at=now - timedelta(days=8), result=QualificationResult.QUALIFIED)
    ]
    dec_pause = policy.evaluate(advertisement=ad, leads=mature_leads, call_attempts=calls, qualification_outcomes=quals, observation_time=now)
    assert dec_pause.action == DecisionAction.CONSIDER_PAUSE
    assert dec_pause.n_contacts == 15
    assert dec_pause.k_qualified == 1
    assert round(dec_pause.observed_qualification, 4) == round(1 / 15, 4)


def test_fixed_budget_redistribution():
    from benchmark.sequential import SequentialClosedLoopRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = SequentialClosedLoopRunner(results_dir=Path(tmpdir))
        res = runner.run_benchmark(
            max_runs_per_scenario=1,
            save_filename="temp_fixed.json",
            budget_mode="fixed_redistributed",
        )

        meta = res["run_metadata"]
        assert meta["budget_mode"] == "fixed_redistributed"

        policies = res["policies"]
        oracle = policies["oracle"]
        qualloop = policies["qualloop"]
        baseline_b = policies["baseline_b"]

        # Oracle allocates 100% of freed budget to good ads from Day 0,
        # achieving highest qualified leads and lowest CPQL among valid full runs
        assert oracle["qualified_leads"] >= qualloop["qualified_leads"]
        assert oracle["cpql"] <= qualloop["cpql"]
        assert qualloop["qualified_leads"] >= baseline_b["qualified_leads"]


def test_per_scenario_counts_sum_to_aggregate():
    """
    Assert that per-scenario seeds, ads, good, poor, and false-pause counts
    sum exactly to the aggregate (100 / 175 / 140 / 35).

    Why Baseline B's per-scenario false pauses implied more than 105:
    False Positive Pause Rate (FPPR) is defined as false_pauses / n_good_ads.
    In scenarios with poor ads (bad_ad_high_engagement: 13 good/13 poor,
    mixed_portfolio: 20 good/10 poor, small_sample_trap: 0 good/12 poor),
    multiplying the scenario false-pause rate by the Total Ads column (175 ads)
    incorrectly inflates the count to ~123.
    When multiplied by the true number of good ads in each scenario
    (45, 24, 13, 0, 13, 10, 20, 7, 8), the per-scenario false pauses are
    31, 18, 10, 0, 10, 9, 15, 7, 5, which sum precisely to 105 (75.00%).
    """
    results_file = Path(__file__).resolve().parent.parent / "benchmark" / "results" / "holdout_sequential.json"
    with open(results_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenarios = data["budget_modes"]["variable"]["scenario_breakdown"]
    policies = ["oracle", "qualloop", "baseline_b", "baseline_a", "baseline_c"]

    total_seeds = sum(sc["n_seeds"] for sc in scenarios.values())
    total_ads = sum(sc["n_ads"] for sc in scenarios.values())
    total_good = sum(sc["n_good"] for sc in scenarios.values())
    total_poor = sum(sc["n_poor"] for sc in scenarios.values())

    assert total_seeds == 100, f"Expected 100 seeds, got {total_seeds}"
    assert total_ads == 175, f"Expected 175 ads, got {total_ads}"
    assert total_good == 140, f"Expected 140 good ads, got {total_good}"
    assert total_poor == 35, f"Expected 35 poor ads, got {total_poor}"

    # Verify healthy_campaign has exactly 15 seeds and 45 ads
    assert scenarios["healthy_campaign"]["n_seeds"] == 15
    assert scenarios["healthy_campaign"]["n_ads"] == 45
    assert scenarios["healthy_campaign"]["budget"] == 150000.0

    # Verify per-policy false pause and missed bad ad sums equal aggregate
    for p in policies:
        agg_fp = data["policy_metrics"][p]["rates_with_95_ci"]["false_positive_pause_rate"]["count"]
        sum_sc_fp = sum(sc[p]["good_ads_false_paused"] for sc in scenarios.values())
        assert sum_sc_fp == agg_fp, f"Policy {p}: sum of per-scenario FP ({sum_sc_fp}) != aggregate ({agg_fp})"

        agg_missed = data["policy_metrics"][p]["rates_with_95_ci"]["missed_bad_ad_rate"]["count"]
        sum_sc_missed = sum(sc[p]["poor_ads_missed"] for sc in scenarios.values())
        assert sum_sc_missed == agg_missed, f"Policy {p}: sum of per-scenario missed ({sum_sc_missed}) != aggregate ({agg_missed})"

    # Specifically verify Baseline B per-scenario false pauses sum to exactly 105
    b_fps = [sc["baseline_b"]["good_ads_false_paused"] for sc in scenarios.values()]
    assert sum(b_fps) == 105, f"Baseline B false pauses must sum to 105, got {sum(b_fps)}"


def test_scenario_stratified_bootstrap_and_per_scenario_paired_differences():
    """Verify stratified bootstrap 95% CIs and per-scenario paired difference reporting."""
    results_file = Path(__file__).resolve().parent.parent / "benchmark" / "results" / "holdout_sequential.json"
    with open(results_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Verify headline policy disclaims single pooled p-value across heterogeneous scenarios
    assert "headline_policy" in data["paired_tests"]
    assert "heterogeneous" in data["paired_tests"]["headline_policy"]

    # 2. Verify all policies have stratified bootstrap 95% intervals
    for p in ["oracle", "qualloop", "baseline_b", "baseline_a", "baseline_c"]:
        pm = data["policy_metrics"][p]
        assert "pooled_ql_per_rupee_bootstrap_ci_95" in pm
        assert len(pm["pooled_ql_per_rupee_bootstrap_ci_95"]) == 2
        assert pm["pooled_ql_per_rupee_bootstrap_ci_95"][0] <= pm["pooled_ql_per_rupee"] <= pm["pooled_ql_per_rupee_bootstrap_ci_95"][1]

        assert "mean_of_per_run_ratios_bootstrap_ci_95" in pm
        assert len(pm["mean_of_per_run_ratios_bootstrap_ci_95"]) == 2
        assert pm["mean_of_per_run_ratios_bootstrap_ci_95"][0] <= pm["mean_of_per_run_ratios"] <= pm["mean_of_per_run_ratios_bootstrap_ci_95"][1]

        assert "mean_qualified_leads_per_run" in pm
        assert "mean_qualified_leads_per_run_bootstrap_ci_95" in pm
        assert len(pm["mean_qualified_leads_per_run_bootstrap_ci_95"]) == 2

    # 3. Verify each scenario has paired differences
    scenarios = data["budget_modes"]["variable"]["scenario_breakdown"]
    for sc_name, sc_data in scenarios.items():
        assert "paired_differences" in sc_data
        for opp in ["baseline_b", "baseline_a", "baseline_c"]:
            key = f"qualloop_minus_{opp}"
            assert key in sc_data["paired_differences"]
            diff_entry = sc_data["paired_differences"][key]
            assert "mean_ql_diff" in diff_entry
            assert "mean_ql_per_rupee_diff" in diff_entry










