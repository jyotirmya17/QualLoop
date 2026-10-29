"""
STEP 4D.3: Controlled Policy Ablation Runner.
Tests the 2x2 Factorial Matrix:
  Config A (Baseline):      Estimator N_min = 12, Policy N_min = 12
  Config B (Estimator-only): Estimator N_min = 20, Policy N_min = 12
  Config C (Policy-only):    Estimator N_min = 12, Policy N_min = 20
  Config D (Both):          Estimator N_min = 20, Policy N_min = 20

Data Separation:
- Untouched Validation Split:
  - Continuous Intent: 50 runs, seeds 22000..22049
  - Bimodal Synthetic: 50 runs, seeds 24000..24049
  - Presets (9 scenarios): 10 seeds each, 26001..26010 (90 runs)
  Total: 190 simulation runs, 450 ads per configuration.
"""

import sys
import json
import math
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
from scipy import stats

backend_root = Path("d:/Developer/qualloop/backend")
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from benchmark.robustness import generate_continuous_scenario
from benchmark.sequential import is_pause
from decision_engine.engine import DecisionPolicy, evaluate_campaign, DecisionAction
from domain.enums import QualificationResult
from estimator.estimator import EstimatorConfig, compute_campaign_estimates
from simulator.engine import run_simulation
from simulator.scenarios import AdConfig, ScenarioConfig, get_scenario, SCENARIO_REGISTRY

HURDLE = 0.15
CHECKPOINTS = [3, 7, 14, 21]

CONFIGS = {
    "A": {
        "name": "Config A (Baseline: Est 12, Pol 12)",
        "estimator_min_mature_contacts": 12,
        "policy_min_mature_contacts": 12,
        "ci_level": 0.80,
        "min_maturity_fraction": 0.50,
        "low_qualification_upper_bound": 0.15,
        "high_cpql_lower_bound": 75.0,
    },
    "B": {
        "name": "Config B (Estimator-only: Est 20, Pol 12)",
        "estimator_min_mature_contacts": 20,
        "policy_min_mature_contacts": 12,
        "ci_level": 0.80,
        "min_maturity_fraction": 0.50,
        "low_qualification_upper_bound": 0.15,
        "high_cpql_lower_bound": 75.0,
    },
    "C": {
        "name": "Config C (Policy-only: Est 12, Pol 20)",
        "estimator_min_mature_contacts": 12,
        "policy_min_mature_contacts": 20,
        "ci_level": 0.80,
        "min_maturity_fraction": 0.50,
        "low_qualification_upper_bound": 0.15,
        "high_cpql_lower_bound": 75.0,
    },
    "D": {
        "name": "Config D (Both: Est 20, Pol 20)",
        "estimator_min_mature_contacts": 20,
        "policy_min_mature_contacts": 20,
        "ci_level": 0.80,
        "min_maturity_fraction": 0.50,
        "low_qualification_upper_bound": 0.15,
        "high_cpql_lower_bound": 75.0,
    },
}

def generate_bimodal_scenario(seed: int, n_ads: int = 3, horizon_days: int = 28) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        is_good = rng.random() < 0.40
        if is_good:
            true_intent = round(float(rng.uniform(0.20, 0.32)), 4)
            label = "good"
        else:
            true_intent = round(float(rng.uniform(0.03, 0.06)), 4)
            label = "bad"
        true_reach = round(float(rng.uniform(0.50, 0.70)), 4)
        ads.append(
            AdConfig(
                creative_id=f"cr-bimodal-{seed}-{i}",
                spend=5000.0,
                impressions=100000,
                clicks=2500,
                true_reachability=true_reach,
                true_intent=true_intent,
                fatigue_enabled=False,
                label=label,
            )
        )
    return ScenarioConfig(
        seed=seed,
        scenario_name="bimodal_intent_synthetic",
        time_horizon_days=horizon_days,
        n_campaigns=1,
        ads_per_campaign=[ads],
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
        leads_per_day_per_ad=5.0,
    )

def build_simulation_dataset(seed_offset: int = 0):
    simulations = []
    # 50 Continuous runs
    for seed in range(22000 + seed_offset, 22050 + seed_offset):
        cfg = generate_continuous_scenario(seed=seed, n_ads=3, hurdle=HURDLE)
        sim = run_simulation(cfg)
        simulations.append({
            "family": "continuous",
            "scenario_name": "continuous_intent",
            "seed": seed,
            "cfg": cfg,
            "sim": sim,
        })

    # 50 Bimodal Synthetic runs
    for seed in range(24000 + seed_offset, 24050 + seed_offset):
        cfg = generate_bimodal_scenario(seed=seed, n_ads=3)
        sim = run_simulation(cfg)
        simulations.append({
            "family": "bimodal_synthetic",
            "scenario_name": "bimodal_intent_synthetic",
            "seed": seed,
            "cfg": cfg,
            "sim": sim,
        })

    # 90 Preset runs (10 seeds each for all 9 presets)
    for p_name in sorted(list(SCENARIO_REGISTRY.keys())):
        for s_idx in range(1, 11):
            seed = 26000 + seed_offset + s_idx
            cfg = get_scenario(p_name, seed=seed)
            sim = run_simulation(cfg)
            simulations.append({
                "family": "preset",
                "scenario_name": p_name,
                "seed": seed,
                "cfg": cfg,
                "sim": sim,
            })

    # Check completeness & uniqueness
    assert len(simulations) == 190, f"Expected 190 simulation runs, got {len(simulations)}"
    sim_keys = [(s["family"], s["scenario_name"], s["seed"]) for s in simulations]
    assert len(set(sim_keys)) == 190, "Duplicate simulation keys found!"
    return simulations

def run_ablation():
    print("=" * 80)
    print("STEP 4D.3: CONTROLLED POLICY ABLATION (A vs B vs C vs D)")
    print("=" * 80)

    simulations = build_simulation_dataset(seed_offset=0)
    print(f"Instantiated {len(simulations)} paired simulation runs.")

    # 1. Compute Never-Paused Reference Baseline
    ref_spend_total = 0.0
    ref_ql_total = 0
    ref_ads_total = 0
    for s in simulations:
        sim = s["sim"]
        for ad in sim.advertisements:
            ref_spend_total += ad.spend
            ref_ads_total += 1
        ref_ql_total += sum(1 for qo in sim.qualification_outcomes if qo.result == QualificationResult.QUALIFIED)

    never_paused_baseline = {
        "total_spend": round(ref_spend_total, 2),
        "total_qualified_leads": ref_ql_total,
        "total_ads": ref_ads_total,
        "macro_cpql": round(ref_spend_total / ref_ql_total, 2) if ref_ql_total > 0 else None,
    }
    print(f"Never-Paused Reference Baseline: Spend = Rs {ref_spend_total:,.2f}, QL = {ref_ql_total}, CPQL = Rs {never_paused_baseline['macro_cpql']:.2f}")

    eval_results = {}

    for cfg_key in ["A", "B", "C", "D"]:
        cfg_info = CONFIGS[cfg_key]
        print(f"\nEvaluating {cfg_key}: {cfg_info['name']}...")

        est_config = EstimatorConfig(
            ci_level=cfg_info["ci_level"],
            min_mature_contacts=cfg_info["estimator_min_mature_contacts"],
            min_maturity_fraction=cfg_info["min_maturity_fraction"],
        )
        dec_policy = DecisionPolicy(
            low_qualification_upper_bound=cfg_info["low_qualification_upper_bound"],
            min_mature_contacts_for_qualification=cfg_info["policy_min_mature_contacts"],
            high_cpql_lower_bound=cfg_info["high_cpql_lower_bound"],
            min_maturity_fraction=cfg_info["min_maturity_fraction"],
        )

        ad_records = []
        run_records = []

        for item in simulations:
            family = item["family"]
            sc_name = item["scenario_name"]
            seed = item["seed"]
            cfg = item["cfg"]
            sim = item["sim"]

            epoch = sim.run.started_at
            horizon = cfg.time_horizon_days
            gt_by_ad = {g.advertisement_id: g for g in sim.ground_truth}

            leads_by_ad = {ad.id: [l for l in sim.leads if l.advertisement_id == ad.id] for ad in sim.advertisements}
            calls_by_ad = {ad.id: [] for ad in sim.advertisements}
            lead_to_ad = {l.id: l.advertisement_id for l in sim.leads}
            for ca in sim.call_attempts:
                ad_id = lead_to_ad.get(ca.lead_id)
                if ad_id:
                    calls_by_ad[ad_id].append(ca)

            quals_by_ad = {ad.id: [] for ad in sim.advertisements}
            qual_by_lead_id = {}
            for qo in sim.qualification_outcomes:
                ad_id = lead_to_ad.get(qo.lead_id)
                if ad_id:
                    quals_by_ad[ad_id].append(qo)
                    if qo.result == QualificationResult.QUALIFIED:
                        qual_by_lead_id[qo.lead_id] = qo

            paused_day = {ad.id: None for ad in sim.advertisements}
            pause_details = {ad.id: None for ad in sim.advertisements}
            run_ie = 0

            # Sequential checkpoints
            for cp_day in CHECKPOINTS:
                t_cp = epoch + np.timedelta64(cp_day, "D").astype("timedelta64[s]").item()

                visible_leads = {ad.id: [l for l in leads_by_ad[ad.id] if l.created_at <= t_cp] for ad in sim.advertisements}
                visible_calls = {ad.id: [c for c in calls_by_ad[ad.id] if c.attempted_at <= t_cp] for ad in sim.advertisements}
                visible_quals = {ad.id: [q for q in quals_by_ad[ad.id] if q.resolved_at <= t_cp] for ad in sim.advertisements}
                accrued_spends = {ad.id: round(ad.spend * (cp_day / horizon), 2) for ad in sim.advertisements}

                active_ads = [ad for ad in sim.advertisements if paused_day[ad.id] is None]
                if not active_ads:
                    continue

                ads_data = [(ad, visible_leads[ad.id], visible_calls[ad.id], visible_quals[ad.id]) for ad in active_ads]
                snaps = compute_campaign_estimates(
                    ads_data=ads_data,
                    observation_time=t_cp,
                    config=est_config,
                    seed=seed,
                )

                decs = evaluate_campaign(
                    snapshots=snaps,
                    ad_spends={ad.id: accrued_spends[ad.id] for ad in active_ads},
                    policy=dec_policy,
                )

                snap_map = {s.advertisement_id: s for s in snaps}
                for dec in decs:
                    snap = snap_map[dec.advertisement_id]
                    action = dec.action

                    if action in (DecisionAction.FLAG_INSUFFICIENT_EVIDENCE, DecisionAction.COLLECT_MORE_DATA):
                        run_ie += 1

                    if is_pause(action) and paused_day[dec.advertisement_id] is None:
                        paused_day[dec.advertisement_id] = cp_day
                        pause_details[dec.advertisement_id] = {
                            "cp_day": cp_day,
                            "action": action.value if hasattr(action, "value") else str(action),
                            "reason": dec.reason,
                            "n_mature_contacts": snap.n_mature_contacts,
                            "k_qualified": snap.k_qualified,
                            "qual_mean": snap.qualification_mean,
                            "qual_ci_high": snap.qualification_ci_high,
                            "evidence_sufficient": snap.evidence_sufficient_qualification,
                        }

            # Compile ad records
            run_spend = 0.0
            run_m1_ql = 0
            run_m2_ql = 0
            run_poor_spend = 0.0
            run_fps = 0
            run_missed_poor = 0

            for ad in sim.advertisements:
                gt = gt_by_ad[ad.id]
                q_true = float(np.mean(gt.true_intent_by_day))
                is_good = (gt.label == "good")
                is_poor = (gt.label == "bad")
                p_day = paused_day[ad.id]

                all_ad_quals = [l for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id]
                full_ql = len(all_ad_quals)

                if p_day is not None:
                    ad_spend = round(ad.spend * (p_day / horizon), 2)
                    t_p = epoch + np.timedelta64(p_day, "D").astype("timedelta64[s]").item()
                    # Metric 1: Pipeline harvest (created before pause)
                    m1_ql = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_p and l.id in qual_by_lead_id)
                    # Metric 2: Strictly resolved at or before pause
                    m2_ql = sum(1 for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id and qual_by_lead_id[l.id].resolved_at <= t_p)
                    if is_good:
                        run_fps += 1
                else:
                    ad_spend = float(ad.spend)
                    m1_ql = full_ql
                    m2_ql = full_ql
                    if is_poor:
                        run_missed_poor += 1

                if is_poor:
                    run_poor_spend += ad_spend

                run_spend += ad_spend
                run_m1_ql += m1_ql
                run_m2_ql += m2_ql

                ad_records.append({
                    "family": family,
                    "scenario_name": sc_name,
                    "ad_id": ad.id,
                    "seed": seed,
                    "true_intent": q_true,
                    "label": gt.label,
                    "is_good": is_good,
                    "is_poor": is_poor,
                    "paused_day": p_day,
                    "spend": ad_spend,
                    "m1_ql": m1_ql,
                    "m2_ql": m2_ql,
                    "pause_details": pause_details[ad.id],
                })

            run_cpql_m1 = round(run_spend / run_m1_ql, 2) if run_m1_ql > 0 else None
            run_records.append({
                "family": family,
                "scenario_name": sc_name,
                "seed": seed,
                "total_spend": round(run_spend, 2),
                "poor_spend": round(run_poor_spend, 2),
                "m1_ql": run_m1_ql,
                "m2_ql": run_m2_ql,
                "cpql_m1": run_cpql_m1,
                "false_pauses": run_fps,
                "missed_poor_ads": run_missed_poor,
                "insufficient_evidence_events": run_ie,
            })

        eval_results[cfg_key] = {
            "config_info": cfg_info,
            "ad_records": ad_records,
            "run_records": run_records,
        }

    # 3. Macro Aggregation and Paired Statistics
    families = ["continuous", "bimodal_synthetic", "preset", "OVERALL"]
    macro_summaries = {}

    for fam in families:
        macro_summaries[fam] = {}
        for cfg_key in ["A", "B", "C", "D"]:
            ads = eval_results[cfg_key]["ad_records"]
            runs = eval_results[cfg_key]["run_records"]
            if fam != "OVERALL":
                ads = [a for a in ads if a["family"] == fam]
                runs = [r for r in runs if r["family"] == fam]

            good_ads = [a for a in ads if a["is_good"]]
            poor_ads = [a for a in ads if a["is_poor"]]
            fps = [a for a in good_ads if a["paused_day"] is not None]
            missed = [a for a in poor_ads if a["paused_day"] is None]
            paused_poor = [a for a in poor_ads if a["paused_day"] is not None]

            poor_pause_days = [a["paused_day"] for a in paused_poor]
            fp_pause_days = [a["paused_day"] for a in fps]

            tot_spend = sum(a["spend"] for a in ads)
            tot_poor_spend = sum(a["spend"] for a in poor_ads)
            tot_m1_ql = sum(a["m1_ql"] for a in ads)
            tot_m2_ql = sum(a["m2_ql"] for a in ads)

            agg_cpql_m1 = round(tot_spend / tot_m1_ql, 2) if tot_m1_ql > 0 else None
            agg_cpql_m2 = round(tot_spend / tot_m2_ql, 2) if tot_m2_ql > 0 else None

            valid_run_cpqls = [r["cpql_m1"] for r in runs if r["cpql_m1"] is not None]
            mean_run_cpql = round(float(np.mean(valid_run_cpqls)), 2) if valid_run_cpqls else None
            median_run_cpql = round(float(np.median(valid_run_cpqls)), 2) if valid_run_cpqls else None
            zero_ql_runs = sum(1 for r in runs if r["m1_ql"] == 0)

            macro_summaries[fam][cfg_key] = {
                "n_runs": len(runs),
                "n_ads": len(ads),
                "n_good": len(good_ads),
                "n_poor": len(poor_ads),
                "false_pauses": len(fps),
                "false_pause_rate": round(len(fps) / len(good_ads), 4) if good_ads else 0.0,
                "missed_poor": len(missed),
                "missed_poor_rate": round(len(missed) / len(poor_ads), 4) if poor_ads else 0.0,
                "paused_poor": len(paused_poor),
                "poor_pause_day_counts": dict(Counter(poor_pause_days)),
                "fp_pause_day_counts": dict(Counter(fp_pause_days)),
                "median_pause_day_poor": float(np.median(poor_pause_days)) if poor_pause_days else None,
                "poor_spend": round(tot_poor_spend, 2),
                "total_spend": round(tot_spend, 2),
                "m1_pipeline_ql": tot_m1_ql,
                "m2_at_pause_ql": tot_m2_ql,
                "macro_cpql_m1_pipeline": agg_cpql_m1,
                "macro_cpql_m2_at_pause": agg_cpql_m2,
                "mean_per_run_cpql_m1": mean_run_cpql,
                "median_per_run_cpql_m1": median_run_cpql,
                "zero_ql_runs_count": zero_ql_runs,
                "insufficient_evidence_events": sum(r["insufficient_evidence_events"] for r in runs),
            }

    # 4. Paired Differences & Bootstrap Inference
    paired_stats = {}
    for fam in families:
        paired_stats[fam] = {}
        runs_a = eval_results["A"]["run_records"]
        if fam != "OVERALL":
            runs_a = [r for r in runs_a if r["family"] == fam]
        run_map_a = {(r["family"], r["scenario_name"], r["seed"]): r for r in runs_a}

        for comp_key in ["B", "C", "D"]:
            runs_comp = eval_results[comp_key]["run_records"]
            if fam != "OVERALL":
                runs_comp = [r for r in runs_comp if r["family"] == fam]
            run_map_comp = {(r["family"], r["scenario_name"], r["seed"]): r for r in runs_comp}

            keys = sorted(list(run_map_a.keys()))
            pairs = [(run_map_a[k], run_map_comp[k]) for k in keys]

            diff_fps = np.array([rc["false_pauses"] - ra["false_pauses"] for ra, rc in pairs])
            diff_missed = np.array([rc["missed_poor_ads"] - ra["missed_poor_ads"] for ra, rc in pairs])
            diff_poor_sp = np.array([rc["poor_spend"] - ra["poor_spend"] for ra, rc in pairs])
            diff_tot_sp = np.array([rc["total_spend"] - ra["total_spend"] for ra, rc in pairs])
            diff_ql = np.array([rc["m1_ql"] - ra["m1_ql"] for ra, rc in pairs])

            def boot(arr):
                rng = np.random.default_rng(42)
                b_means = [np.mean(rng.choice(arr, size=len(arr), replace=True)) for _ in range(5000)]
                t_stat, p_val = stats.ttest_1samp(arr, 0.0) if np.std(arr) > 1e-9 else (0.0, 1.0)
                try:
                    w_stat, w_pval = stats.wilcoxon(arr) if np.any(arr != 0) else (0.0, 1.0)
                except Exception:
                    w_pval = 1.0
                return {
                    "mean_diff": round(float(np.mean(arr)), 4),
                    "ci_95": [round(float(np.percentile(b_means, 2.5)), 4), round(float(np.percentile(b_means, 97.5)), 4)],
                    "p_paired_t": float(p_val),
                    "p_wilcoxon": float(w_pval),
                }

            paired_stats[fam][f"{comp_key}_minus_A"] = {
                "n_pairs": len(pairs),
                "false_pauses": boot(diff_fps),
                "missed_poor_ads": boot(diff_missed),
                "poor_spend": boot(diff_poor_sp),
                "total_spend": boot(diff_tot_sp),
                "qualified_leads": boot(diff_ql),
            }

    output_data = {
        "metadata": {
            "version": "v1_step4d3_controlled_ablation",
            "executed_at": "2026-10-27T20:15:00Z",
            "description": "2x2 factorial ablation of Estimator N_min (12 vs 20) and Policy N_min (12 vs 20)",
            "validation_split": "Untouched Precommitted Seeds (22000 continuous, 24000 bimodal, 26000 presets)",
            "total_runs": 190,
            "total_ads_per_config": 450,
            "ci_level_held_constant": 0.80,
            "linear_returns_model": "Spend^1.0",
        },
        "never_paused_reference_baseline": never_paused_baseline,
        "macro_summaries": macro_summaries,
        "paired_statistics": paired_stats,
        "eval_results": eval_results,
    }

    # Save to JSON
    out_json = Path("scratch/policy_ablation_results_v1.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"\nSaved structured ablation results to {out_json}")

    return output_data

if __name__ == "__main__":
    run_ablation()
