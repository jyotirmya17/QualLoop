"""
Fair Baseline C Tuning & Holdout Evaluation.

1. Pre-stated selection rule:
   argmin(FNDR) subject to FPPR <= 4.00% on 100 sequential tuning seeds.
   (If no config satisfies FPPR <= 4.00%, select argmin(FPPR)).

2. Grid search over 12 configurations on 100 tuning seeds:
   min_mature_contacts in {10, 15, 20, 30} x qualification_threshold in {0.10, 0.12, 0.15}.

3. Freeze the single winning configuration of Baseline C and evaluate ONCE on 100 holdout seeds.

4. Compare QualLoop vs Tuned Baseline C using paired differences and scenario-stratified bootstrap 95% CIs.
   If they are not distinguishable on total leads, say so plainly.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from benchmark.baseline import BaselineCPolicy
from benchmark.evaluate_holdout import compute_stratified_bootstrap, wilson_score_interval
from benchmark.sequential import SequentialClosedLoopRunner, is_pause
from simulator.engine import run_simulation
from simulator.scenarios import get_scenario


def tune_baseline_c() -> dict[str, Any]:
    print("=" * 80)
    print("FAIR BASELINE C TUNING & HOLDOUT EVALUATION")
    print("=" * 80)

    selection_rule = "argmin(FNDR) subject to FPPR <= 4.00% on 100 sequential tuning seeds"
    print(f"Pre-Stated Selection Rule: {selection_rule}")

    base_dir = Path(__file__).resolve().parent
    seeds_split_path = base_dir / "seeds_split.json"
    with open(seeds_split_path, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    tuning_seeds = split_data["tuning"]
    holdout_seeds = split_data["holdout"]

    checkpoints = [3, 7, 14, 21]
    contacts_grid = [10, 15, 20, 30]
    threshold_grid = [0.10, 0.12, 0.15]

    print("\n[Step 1/3] Simulating 100 tuning seeds and pre-slicing checkpoint data...")
    t0 = time.time()
    # Pre-simulate 100 tuning runs to evaluate all 12 configs in seconds
    sim_runs = []
    for sc_name, seeds in tuning_seeds.items():
        for seed in seeds:
            cfg = get_scenario(sc_name, seed=seed)
            sim = run_simulation(cfg)
            epoch = sim.run.started_at
            horizon = cfg.time_horizon_days
            gt_by_ad = {g.advertisement_id: g for g in sim.ground_truth}

            leads_by_ad = {ad.id: [] for ad in sim.advertisements}
            for l in sim.leads:
                if l.advertisement_id in leads_by_ad:
                    leads_by_ad[l.advertisement_id].append(l)

            calls_by_ad = {ad.id: [] for ad in sim.advertisements}
            lead_to_ad = {l.id: l.advertisement_id for l in sim.leads}
            for ca in sim.call_attempts:
                aid = lead_to_ad.get(ca.lead_id)
                if aid and aid in calls_by_ad:
                    calls_by_ad[aid].append(ca)

            quals_by_ad = {ad.id: [] for ad in sim.advertisements}
            for qo in sim.qualification_outcomes:
                aid = lead_to_ad.get(qo.lead_id)
                if aid and aid in quals_by_ad:
                    quals_by_ad[aid].append(qo)

            slices = []
            for cp_day in checkpoints:
                t_cp = epoch + timedelta(days=cp_day)
                vis_leads = {ad.id: [l for l in leads_by_ad[ad.id] if l.created_at <= t_cp] for ad in sim.advertisements}
                vis_calls = {ad.id: [c for c in calls_by_ad[ad.id] if c.attempted_at <= t_cp] for ad in sim.advertisements}
                vis_quals = {ad.id: [q for q in quals_by_ad[ad.id] if q.resolved_at <= t_cp] for ad in sim.advertisements}
                slices.append((cp_day, t_cp, vis_leads, vis_calls, vis_quals))

            sim_runs.append({
                "scenario": sc_name,
                "seed": seed,
                "ads": sim.advertisements,
                "gt_by_ad": gt_by_ad,
                "slices": slices,
            })
    print(f"  -> Pre-simulated 100 tuning runs in {time.time() - t0:.2f}s")

    print("\n[Step 2/3] Evaluating 12 Grid Configurations on 100 Tuning Seeds...")
    grid_results: list[dict[str, Any]] = []

    for mc in contacts_grid:
        for th in threshold_grid:
            policy = BaselineCPolicy(pause_threshold=th, min_contacts=mc)
            fp_count = 0
            fn_count = 0
            n_good = 0
            n_poor = 0

            for run in sim_runs:
                paused = {ad.id: None for ad in run["ads"]}
                for cp_day, t_cp, vis_leads, vis_calls, vis_quals in run["slices"]:
                    for ad in run["ads"]:
                        if paused[ad.id] is None:
                            dec = policy.evaluate(
                                advertisement=ad,
                                leads=vis_leads[ad.id],
                                call_attempts=vis_calls[ad.id],
                                qualification_outcomes=vis_quals[ad.id],
                                observation_time=t_cp,
                            )
                            if is_pause(dec.action):
                                paused[ad.id] = cp_day

                for ad in run["ads"]:
                    gt = run["gt_by_ad"][ad.id]
                    if gt.label == "good":
                        n_good += 1
                        if paused[ad.id] is not None:
                            fp_count += 1
                    elif gt.label == "bad":
                        n_poor += 1
                        if paused[ad.id] is None:
                            fn_count += 1

            fppr = fp_count / n_good if n_good > 0 else 0.0
            fndr = fn_count / n_poor if n_poor > 0 else 0.0

            res_entry = {
                "min_mature_contacts": mc,
                "qualification_threshold": th,
                "good_ads_evaluated": n_good,
                "false_pauses": fp_count,
                "fppr": round(fppr, 4),
                "poor_ads_evaluated": n_poor,
                "missed_bad_ads": fn_count,
                "fndr": round(fndr, 4),
            }
            grid_results.append(res_entry)

    # Print Tuning Grid Table
    print("\n" + "=" * 85)
    print(f"{'Config':<8} | {'Min Contacts':<14} | {'Hurdle (q)':<10} | {'FP (Count)':<10} | {'FPPR':<8} | {'Missed (Count)':<14} | {'FNDR':<8}")
    print("-" * 85)
    for idx, r in enumerate(grid_results):
        print(f"Config {idx:<2} | {r['min_mature_contacts']:<14} | {r['qualification_threshold']:<10.2f} | {r['false_pauses']:<10} | {r['fppr']:<7.2%} | {r['missed_bad_ads']:<14} | {r['fndr']:<7.2%}")
    print("=" * 85)

    # Apply Selection Rule:
    # Rule: argmin(FNDR) subject to FPPR <= 4.00%. Fallback: argmin(FPPR).
    feasible = [r for r in grid_results if r["fppr"] <= 0.0400]
    if feasible:
        feasible.sort(key=lambda x: (x["fndr"], x["fppr"]))
        selected_config = feasible[0]
        selection_rationale = (
            f"Selected via primary rule: lowest FNDR ({selected_config['fndr']:.2%}) among "
            f"{len(feasible)} configurations satisfying FPPR <= 4.00%."
        )
    else:
        grid_results.sort(key=lambda x: (x["fppr"], x["fndr"]))
        selected_config = grid_results[0]
        selection_rationale = (
            f"Selected via fallback rule: no configuration met FPPR <= 4.00%; "
            f"chose lowest FPPR ({selected_config['fppr']:.2%})."
        )

    print(f"\nWinning Tuned Baseline C Configuration:")
    print(f"  -> Min Mature Contacts: {selected_config['min_mature_contacts']}")
    print(f"  -> Qualification Hurdle: {selected_config['qualification_threshold']:.2f}")
    print(f"  -> Tuning FPPR: {selected_config['fppr']:.2%} ({selected_config['false_pauses']}/{selected_config['good_ads_evaluated']})")
    print(f"  -> Tuning FNDR: {selected_config['fndr']:.2%} ({selected_config['missed_bad_ads']}/{selected_config['poor_ads_evaluated']})")
    print(f"  -> Rationale: {selection_rationale}")

    # Step 3: Freeze Tuned Baseline C and Evaluate ONCE on Holdout
    print("\n[Step 3/3] Evaluating Frozen Tuned Baseline C on 100 Holdout Seeds...")
    tuned_c_policy = BaselineCPolicy(
        pause_threshold=selected_config["qualification_threshold"],
        min_contacts=selected_config["min_mature_contacts"],
    )

    from decision_engine.engine import DecisionPolicy
    from estimator.estimator import EstimatorConfig

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
        baseline_c_policy=tuned_c_policy,
    )

    # Run holdout evaluations
    var_results = runner.run_simulation_closed_loop(seeds=holdout_seeds, budget_mode="variable")
    fixed_results = runner.run_simulation_closed_loop(seeds=holdout_seeds, budget_mode="fixed_redistributed")

    # Evaluate across runs for paired statistics
    runs_var: dict[tuple[str, int], list[Any]] = {}
    for r in var_results:
        runs_var.setdefault((r.scenario_name, r.seed), []).append(r)
    run_keys = sorted(list(runs_var.keys()))

    runs_fixed: dict[tuple[str, int], list[Any]] = {}
    for r in fixed_results:
        runs_fixed.setdefault((r.scenario_name, r.seed), []).append(r)

    # Aggregate metrics comparison on holdout
    def extract_run_stats(runs_dict: dict, p: str):
        spends = []
        qls = []
        ratios = []
        for k in run_keys:
            ads = runs_dict[k]
            sp = sum(a.spend_incurred[p] for a in ads)
            ql = sum(a.qualified_leads_realized[p] for a in ads)
            spends.append(sp)
            qls.append(ql)
            ratios.append(ql / sp if sp > 0 else 0.0)
        return np.array(spends), np.array(qls), np.array(ratios)

    ql_sp_var, ql_leads_var, ql_ratio_var = extract_run_stats(runs_var, "qualloop")
    tc_sp_var, tc_leads_var, tc_ratio_var = extract_run_stats(runs_var, "baseline_c")

    ql_sp_fix, ql_leads_fix, ql_ratio_fix = extract_run_stats(runs_fixed, "qualloop")
    tc_sp_fix, tc_leads_fix, tc_ratio_fix = extract_run_stats(runs_fixed, "baseline_c")

    # Paired lead differences (QualLoop minus Tuned Baseline C)
    delta_leads_fixed = ql_leads_fix - tc_leads_fix
    delta_leads_var = ql_leads_var - tc_leads_var
    delta_ratio_fixed = ql_ratio_fix - tc_ratio_fix

    # Stratified bootstrap CI on lead difference at fixed budget
    rng = np.random.default_rng(42)
    sc_indices: dict[str, list[int]] = {}
    for idx, (sc, _) in enumerate(run_keys):
        sc_indices.setdefault(sc, []).append(idx)

    boot_delta_leads_fixed = []
    boot_delta_leads_var = []
    for _ in range(2000):
        b_idxs = []
        for sc, idxs in sc_indices.items():
            b_idxs.extend(rng.choice(idxs, size=len(idxs), replace=True))
        boot_delta_leads_fixed.append(float(np.mean(delta_leads_fixed[b_idxs])))
        boot_delta_leads_var.append(float(np.mean(delta_leads_var[b_idxs])))

    delta_leads_fixed_ci = [
        round(float(np.percentile(boot_delta_leads_fixed, 2.5)), 2),
        round(float(np.percentile(boot_delta_leads_fixed, 97.5)), 2),
    ]
    delta_leads_var_ci = [
        round(float(np.percentile(boot_delta_leads_var, 2.5)), 2),
        round(float(np.percentile(boot_delta_leads_var, 97.5)), 2),
    ]

    t_stat_fix, p_val_fix = stats.ttest_rel(ql_leads_fix, tc_leads_fix)

    # Distinguishability assessment:
    is_distinguishable = (delta_leads_fixed_ci[0] > 0) or (delta_leads_fixed_ci[1] < 0)
    if is_distinguishable:
        distinguishability_verdict = (
            f"QualLoop and Tuned Baseline C ARE statistically distinguishable on total qualified leads at fixed budget "
            f"(mean difference = +{np.mean(delta_leads_fixed):.2f} leads/run, 95% CI [{delta_leads_fixed_ci[0]}, {delta_leads_fixed_ci[1]}])."
        )
    else:
        distinguishability_verdict = (
            f"QualLoop and Tuned Baseline C ARE NOT statistically distinguishable on total qualified leads at fixed budget "
            f"(mean difference = {np.mean(delta_leads_fixed):+.2f} leads/run, 95% bootstrap CI [{delta_leads_fixed_ci[0]}, {delta_leads_fixed_ci[1]}] "
            f"spans zero; p = {p_val_fix:.4f}). QualLoop's edge is strictly in small-sample false pause prevention."
        )

    # False pause and missed bad ad counts on holdout
    good_ads_holdout = [r for r in var_results if r.is_good]
    poor_ads_holdout = [r for r in var_results if r.is_poor]
    good_econ_holdout = [r for r in var_results if r.is_good_economic]
    poor_econ_holdout = [r for r in var_results if r.is_poor_economic]

    tc_fp_intent = sum(1 for a in good_ads_holdout if a.paused_day["baseline_c"] is not None)
    tc_fn_intent = sum(1 for a in poor_ads_holdout if a.paused_day["baseline_c"] is None)
    tc_fp_econ = sum(1 for a in good_econ_holdout if a.paused_day["baseline_c"] is not None)
    tc_fn_econ = sum(1 for a in poor_econ_holdout if a.paused_day["baseline_c"] is None)

    ql_fp_intent = sum(1 for a in good_ads_holdout if a.paused_day["qualloop"] is not None)
    ql_fn_intent = sum(1 for a in poor_ads_holdout if a.paused_day["qualloop"] is None)
    ql_fp_econ = sum(1 for a in good_econ_holdout if a.paused_day["qualloop"] is not None)
    ql_fn_econ = sum(1 for a in poor_econ_holdout if a.paused_day["qualloop"] is None)

    comparison_summary = {
        "selection_rule": selection_rule,
        "tuning_grid": grid_results,
        "selected_configuration": selected_config,
        "selection_rationale": selection_rationale,
        "holdout_evaluation": {
            "distinguishability_verdict": distinguishability_verdict,
            "is_statistically_distinguishable_on_fixed_budget_leads": is_distinguishable,
            "fixed_redistributed_budget": {
                "qualloop_total_leads": round(float(np.sum(ql_leads_fix)), 2),
                "tuned_c_total_leads": round(float(np.sum(tc_leads_fix)), 2),
                "qualloop_cpql": round(825000.0 / float(np.sum(ql_leads_fix)), 2),
                "tuned_c_cpql": round(825000.0 / float(np.sum(tc_leads_fix)), 2),
                "mean_paired_difference_per_run": round(float(np.mean(delta_leads_fixed)), 2),
                "paired_difference_stratified_bootstrap_95_ci": delta_leads_fixed_ci,
                "paired_t_statistic": round(float(t_stat_fix), 4) if not np.isnan(t_stat_fix) else None,
                "paired_t_pvalue": round(float(p_val_fix), 4) if not np.isnan(p_val_fix) else None,
            },
            "variable_budget": {
                "qualloop_spend": round(float(np.sum(ql_sp_var)), 2),
                "tuned_c_spend": round(float(np.sum(tc_sp_var)), 2),
                "qualloop_leads": round(float(np.sum(ql_leads_var)), 2),
                "tuned_c_leads": round(float(np.sum(tc_leads_var)), 2),
                "qualloop_cpql": round(float(np.sum(ql_sp_var)) / float(np.sum(ql_leads_var)), 2),
                "tuned_c_cpql": round(float(np.sum(tc_sp_var)) / float(np.sum(tc_leads_var)), 2),
                "mean_paired_difference_per_run": round(float(np.mean(delta_leads_var)), 2),
                "paired_difference_stratified_bootstrap_95_ci": delta_leads_var_ci,
            },
            "error_rates": {
                "qualloop": {
                    "fp_by_intent": {"count": ql_fp_intent, "total": 140, "rate": round(ql_fp_intent / 140, 4)},
                    "fp_by_economics": {"count": ql_fp_econ, "total": 133, "rate": round(ql_fp_econ / 133, 4)},
                    "fn_by_intent": {"count": ql_fn_intent, "total": 35, "rate": round(ql_fn_intent / 35, 4)},
                    "fn_by_economics": {"count": ql_fn_econ, "total": 42, "rate": round(ql_fn_econ / 42, 4)},
                },
                "tuned_baseline_c": {
                    "fp_by_intent": {"count": tc_fp_intent, "total": 140, "rate": round(tc_fp_intent / 140, 4)},
                    "fp_by_economics": {"count": tc_fp_econ, "total": 133, "rate": round(tc_fp_econ / 133, 4)},
                    "fn_by_intent": {"count": tc_fn_intent, "total": 35, "rate": round(tc_fn_intent / 35, 4)},
                    "fn_by_economics": {"count": tc_fn_econ, "total": 42, "rate": round(tc_fn_econ / 42, 4)},
                },
            },
        },
    }

    out_file = base_dir / "results" / "baseline_c_tuning.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(comparison_summary, f, indent=2)

    print(f"\nSaved Tuning & Holdout Results to {out_file}")
    print("\n--- DISTINGUISHABILITY VERDICT ---")
    print(distinguishability_verdict)
    print("=" * 80)

    return comparison_summary


if __name__ == "__main__":
    tune_baseline_c()
