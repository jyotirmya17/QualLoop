"""
Holdout Sequential Closed-Loop Evaluation (Frozen Policy).

Evaluates the frozen tuned policy (Config 2) on the 100 holdout seeds ONLY.
Evaluates against:
- Oracle (pauses poor ads at Day 0)
- Baseline B (naive qualification heuristic; counts unreached/pending as failures)
- Baseline A (top-of-funnel optimizer on CTR and CPL only)

Computes:
- Item-3 closed-loop metrics (cumulative spend, qualified leads, QL/rupee, spend on poor ads,
  leads forgone from good ads, days to pause).
- 95% confidence intervals (Wilson score interval for rates).
- Paired statistical tests (paired t-test and Wilcoxon signed-rank test across the 100 runs).
- Per-scenario breakdown identifying every scenario where QualLoop loses.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy import stats

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from benchmark.sequential import SequentialClosedLoopRunner, AdSequentialResult
from decision_engine.engine import DecisionPolicy
from estimator.estimator import EstimatorConfig


def wilson_score_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """Calculate 95% Wilson score confidence interval for binomial proportion."""
    if trials == 0:
        return (0.0, 0.0)
    z = stats.norm.ppf((1 + confidence) / 2)
    p = successes / trials
    denom = 1 + (z**2) / trials
    center = (p + (z**2) / (2 * trials)) / denom
    margin = (z / denom) * math.sqrt((p * (1 - p) / trials) + (z**2) / (4 * (trials**2)))
    low = max(0.0, center - margin)
    high = min(1.0, center + margin)
    return (round(low, 4), round(high, 4))


def run_holdout_evaluation(
    save_filename: str = "holdout_sequential.json",
) -> dict[str, Any]:
    base_dir = Path(__file__).resolve().parent
    seeds_split_path = base_dir / "seeds_split.json"

    with open(seeds_split_path, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    holdout_seeds: dict[str, list[int]] = split_data["holdout"]
    n_simulations = sum(len(seeds) for seeds in holdout_seeds.values())

    # Frozen tuned policy (Config 2)
    frozen_policy = DecisionPolicy(
        low_qualification_upper_bound=0.15,
        min_mature_contacts_for_qualification=12,
        high_cpql_lower_bound=75.0,
        min_maturity_fraction=0.50,
    )
    frozen_estimator_config = EstimatorConfig(
        ci_level=0.80,
        min_mature_contacts=12,
        min_maturity_fraction=0.50,
    )

    runner = SequentialClosedLoopRunner(
        seeds_path=seeds_split_path,
        decision_policy=frozen_policy,
        estimator_config=frozen_estimator_config,
    )

    ad_results = runner.run_simulation_closed_loop(seeds=holdout_seeds)

    n_ads = len(ad_results)
    good_ads = [r for r in ad_results if r.is_good]
    poor_ads = [r for r in ad_results if r.is_poor]
    n_good = len(good_ads)
    n_poor = len(poor_ads)

    policies = ["oracle", "qualloop", "baseline_b", "baseline_a"]

    # 1. Oracle baseline
    oracle_spend = sum(r.spend_incurred["oracle"] for r in ad_results)
    oracle_ql = sum(r.qualified_leads_realized["oracle"] for r in ad_results)
    oracle_ql_per_rupee = oracle_ql / oracle_spend if oracle_spend > 0 else 0.0

    # 2. Per-policy metrics
    policy_metrics: dict[str, dict[str, Any]] = {}
    for p in policies:
        summary = runner.summarize_policy(p, ad_results, oracle_ql_per_rupee)
        sum_dict = asdict(summary)

        # Rates and 95% Wilson intervals
        # False Positive Pause Rate (on good ads)
        fp_count = summary.good_ads_false_paused
        fppr = summary.good_ads_false_pause_rate
        fppr_ci = wilson_score_interval(fp_count, n_good, 0.95)

        # Missed Bad Ad Rate (FNDR on poor ads)
        fndr_count = summary.poor_ads_missed
        fndr = fndr_count / n_poor if n_poor > 0 else 0.0
        fndr_ci = wilson_score_interval(fndr_count, n_poor, 0.95)

        sum_dict["rates_with_95_ci"] = {
            "false_positive_pause_rate": {
                "count": fp_count,
                "total": n_good,
                "rate": round(fppr, 4),
                "ci_95": fppr_ci,
            },
            "missed_bad_ad_rate": {
                "count": fndr_count,
                "total": n_poor,
                "rate": round(fndr, 4),
                "ci_95": fndr_ci,
            },
        }
        policy_metrics[p] = sum_dict

    # 3. Paired statistical tests across simulations (N = 100 runs)
    # Group results by (scenario_name, seed)
    runs: dict[tuple[str, int], list[AdSequentialResult]] = {}
    for r in ad_results:
        key = (r.scenario_name, r.seed)
        runs.setdefault(key, []).append(r)

    # Compute per-run QL/rupee and total QL for each policy
    run_keys = sorted(list(runs.keys()))
    run_data = {p: {"ql_per_rupee": [], "qualified_leads": [], "spend": []} for p in policies}

    for key in run_keys:
        run_ads = runs[key]
        for p in policies:
            sp = sum(a.spend_incurred[p] for a in run_ads)
            ql = sum(a.qualified_leads_realized[p] for a in run_ads)
            run_data[p]["spend"].append(sp)
            run_data[p]["qualified_leads"].append(ql)
            run_data[p]["ql_per_rupee"].append(ql / sp if sp > 0 else 0.0)

    paired_tests = {}
    for opponent in ["baseline_b", "baseline_a", "oracle"]:
        # QL per rupee test
        ql_diff = np.array(run_data["qualloop"]["ql_per_rupee"]) - np.array(run_data[opponent]["ql_per_rupee"])
        t_stat, p_val = stats.ttest_rel(run_data["qualloop"]["ql_per_rupee"], run_data[opponent]["ql_per_rupee"])

        # Wilcoxon test (handle zero differences)
        try:
            w_res = stats.wilcoxon(run_data["qualloop"]["ql_per_rupee"], run_data[opponent]["ql_per_rupee"])
            w_stat, w_pval = float(w_res.statistic), float(w_res.pvalue)
        except Exception:
            w_stat, w_pval = None, None

        # Qualified leads difference
        leads_diff = np.array(run_data["qualloop"]["qualified_leads"]) - np.array(run_data[opponent]["qualified_leads"])
        t_stat_l, p_val_l = stats.ttest_rel(run_data["qualloop"]["qualified_leads"], run_data[opponent]["qualified_leads"])

        paired_tests[f"qualloop_vs_{opponent}"] = {
            "ql_per_rupee": {
                "mean_diff": round(float(np.mean(ql_diff)), 6),
                "std_diff": round(float(np.std(ql_diff)), 6),
                "paired_t_statistic": round(float(t_stat), 4) if not np.isnan(t_stat) else None,
                "paired_t_pvalue": float(p_val) if not np.isnan(p_val) else None,
                "wilcoxon_statistic": w_stat,
                "wilcoxon_pvalue": w_pval,
            },
            "qualified_leads": {
                "mean_diff": round(float(np.mean(leads_diff)), 2),
                "std_diff": round(float(np.std(leads_diff)), 2),
                "paired_t_statistic": round(float(t_stat_l), 4) if not np.isnan(t_stat_l) else None,
                "paired_t_pvalue": float(p_val_l) if not np.isnan(p_val_l) else None,
            },
        }

    # 4. Scenario-by-scenario breakdown to identify every scenario where QualLoop loses
    scenario_breakdown: dict[str, dict[str, Any]] = {}
    scenario_names = sorted(list({r.scenario_name for r in ad_results}))

    for sc in scenario_names:
        sc_ads = [r for r in ad_results if r.scenario_name == sc]
        sc_dict = {}
        for p in policies:
            sc_spend = sum(a.spend_incurred[p] for a in sc_ads)
            sc_ql = sum(a.qualified_leads_realized[p] for a in sc_ads)
            sc_poor = [a for a in sc_ads if a.is_poor]
            sc_good = [a for a in sc_ads if a.is_good]
            sc_poor_spend = sum(a.spend_incurred[p] for a in sc_poor)
            sc_lost_ql = sum(a.qualified_leads_forgone[p] for a in sc_good)
            sc_dict[p] = {
                "spend": round(sc_spend, 2),
                "qualified_leads": sc_ql,
                "ql_per_rupee": round(sc_ql / sc_spend, 6) if sc_spend > 0 else 0.0,
                "spend_on_poor_ads": round(sc_poor_spend, 2),
                "forgone_good_ql": sc_lost_ql,
                "good_ads_false_paused": sum(1 for a in sc_good if a.paused_day[p] is not None),
                "poor_ads_missed": sum(1 for a in sc_poor if a.paused_day[p] is None),
            }

        # Compare QualLoop against baselines for this scenario
        ql_vs_b = sc_dict["qualloop"]["ql_per_rupee"] - sc_dict["baseline_b"]["ql_per_rupee"]
        ql_vs_a = sc_dict["qualloop"]["ql_per_rupee"] - sc_dict["baseline_a"]["ql_per_rupee"]
        leads_vs_b = sc_dict["qualloop"]["qualified_leads"] - sc_dict["baseline_b"]["qualified_leads"]
        leads_vs_a = sc_dict["qualloop"]["qualified_leads"] - sc_dict["baseline_a"]["qualified_leads"]

        losses = []
        if ql_vs_b < -1e-6:
            losses.append(f"Loses to Baseline B on QL/rupee ({sc_dict['qualloop']['ql_per_rupee']} vs {sc_dict['baseline_b']['ql_per_rupee']})")
        if ql_vs_a < -1e-6:
            losses.append(f"Loses to Baseline A on QL/rupee ({sc_dict['qualloop']['ql_per_rupee']} vs {sc_dict['baseline_a']['ql_per_rupee']})")
        if leads_vs_b < 0:
            losses.append(f"Loses to Baseline B on qualified leads ({sc_dict['qualloop']['qualified_leads']} vs {sc_dict['baseline_b']['qualified_leads']})")
        if leads_vs_a < 0:
            losses.append(f"Loses to Baseline A on qualified leads ({sc_dict['qualloop']['qualified_leads']} vs {sc_dict['baseline_a']['qualified_leads']})")

        sc_dict["comparison"] = {
            "qualloop_vs_baseline_b_ql_diff": leads_vs_b,
            "qualloop_vs_baseline_a_ql_diff": leads_vs_a,
            "qualloop_loses": len(losses) > 0,
            "loss_reasons": losses,
        }
        scenario_breakdown[sc] = sc_dict

    output = {
        "metadata": {
            "experiment": "holdout_sequential_evaluation",
            "policy": "Config 2 (Frozen)",
            "policy_parameters": {
                "low_qualification_upper_bound": frozen_policy.low_qualification_upper_bound,
                "min_mature_contacts_for_qualification": frozen_policy.min_mature_contacts_for_qualification,
                "high_cpql_lower_bound": frozen_policy.high_cpql_lower_bound,
                "min_maturity_fraction": frozen_policy.min_maturity_fraction,
                "credible_interval_level": frozen_estimator_config.ci_level,
            },
            "selection_rule": "argmin(FNDR) subject to FPPR == 0.00% on 100 tuning seeds",
            "seeds_file_used": "seeds_split.json",
            "split_evaluated": "holdout",
            "n_simulations": n_simulations,
            "n_scenarios": len(scenario_names),
            "n_ads": n_ads,
            "n_good": n_good,
            "n_poor": n_poor,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        },
        "policy_metrics": policy_metrics,
        "paired_tests": paired_tests,
        "scenario_breakdown": scenario_breakdown,
    }

    results_dir = base_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    out_file = results_dir / save_filename
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    return output


if __name__ == "__main__":
    print("Evaluating Frozen Config 2 on 100 Holdout Seeds (Sequential Closed-Loop)...")
    res = run_holdout_evaluation()
    print("--- POLICY METRICS ---")
    print(json.dumps(res["policy_metrics"], indent=2))
    print("--- PAIRED TESTS ---")
    print(json.dumps(res["paired_tests"], indent=2))
    print("--- SCENARIO LOSSES ---")
    for sc, data in res["scenario_breakdown"].items():
        comp = data["comparison"]
        if comp["qualloop_loses"]:
            print(f"Scenario '{sc}': {comp['loss_reasons']}")
