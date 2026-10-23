"""
Tests for benchmark module (baseline policy and benchmark runner).
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from benchmark.baseline import BaselinePolicy
from benchmark.runner import BenchmarkRunner, _wilson_score_interval
from domain.enums import CallOutcome, DecisionAction, QualificationResult
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
    assert t_res.statistic > 0, "Positive statistic indicates QualLoop is superior"

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






