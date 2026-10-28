"""
Step 4D.5: Benchmark Semantics Alignment & Economic Regret Evaluation Runner

Evaluates the exact same frozen policies and paired simulation scenarios under two
independent scoring definitions:
- Scoring View 1: Business Hurdle = 10% (tau_biz = 0.10)
- Scoring View 2: Business Hurdle = 15% (tau_biz = 0.15)

Evaluated Policies:
- PROD_P10: Unmodified Production Policy (ci=0.90, N_min=20, thresh=0.10)
- PROD_P15: Production Policy configured for 15% hurdle (ci=0.90, N_min=20, thresh=0.15)
- CONFIG_A_P15: Step 4D Benchmark Config A (ci=0.80, N_min=12, thresh=0.15)

Preserves exact paired simulation runs:
- 50 continuous intent runs (seeds 22000-22049)
- 50 bimodal synthetic runs (seeds 24000-24049)
- 90 preset runs (10 seeds x 9 presets, seeds 26001-26010)
Total: 190 runs, 450 ads.
"""

import json
import math
import os
import sys
from typing import Dict, Any, List, Tuple

import numpy as np
import scipy.stats as stats

sys.path.append(os.path.abspath("backend"))

from benchmark.sequential import is_pause
from decision_engine.engine import DecisionPolicy, evaluate_campaign, DecisionAction
from domain.enums import QualificationResult
from estimator.estimator import EstimatorConfig, compute_campaign_estimates
from simulator.engine import run_simulation
from simulator.scenarios import AdConfig, ScenarioConfig, get_scenario, SCENARIO_REGISTRY

CHECKPOINTS = [3, 7, 14, 21]

def wilson_score_ci(k: int, n: int, conf: float = 0.95) -> Tuple[float, float, float]:
    """Calculates Wilson score confidence interval for binomial proportion."""
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = k / n
    z = stats.norm.ppf(1.0 - (1.0 - conf) / 2.0)
    denom = 1.0 + (z**2) / n
    centre = (p + (z**2) / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))) / denom
    return float(p), float(max(0.0, centre - spread)), float(min(1.0, centre + spread))

def generate_continuous_scenario(seed: int, n_ads: int = 3, hurdle: float = 0.15) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        true_intent = round(float(rng.uniform(0.05, 0.25)), 4)
        true_reach = round(float(rng.uniform(0.40, 0.70)), 4)
        ads.append(
            AdConfig(
                creative_id=f"cr-cont-{seed}-{i}",
                spend=5000.0,
                impressions=100000,
                clicks=2500,
                true_reachability=true_reach,
                true_intent=true_intent,
                fatigue_enabled=False,
                label="unlabelled",  # Label assigned dynamically by scoring view
            )
        )
    return ScenarioConfig(
        seed=seed,
        scenario_name="continuous_intent",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[ads],
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
        leads_per_day_per_ad=5.0,
    )

def generate_bimodal_scenario(seed: int, n_ads: int = 3) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        is_high = rng.random() < 0.40
        if is_high:
            true_intent = round(float(rng.uniform(0.20, 0.32)), 4)
        else:
            true_intent = round(float(rng.uniform(0.03, 0.06)), 4)
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
                label="unlabelled",
            )
        )
    return ScenarioConfig(
        seed=seed,
        scenario_name="bimodal_intent_synthetic",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[ads],
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
        leads_per_day_per_ad=5.0,
    )

def build_dataset() -> List[Dict[str, Any]]:
    simulations = []
    for seed in range(22000, 22050):
        cfg = generate_continuous_scenario(seed=seed, n_ads=3)
        sim = run_simulation(cfg)
        simulations.append({"family": "continuous", "scenario_name": "continuous_intent", "seed": seed, "cfg": cfg, "sim": sim})

    for seed in range(24000, 24050):
        cfg = generate_bimodal_scenario(seed=seed, n_ads=3)
        sim = run_simulation(cfg)
        simulations.append({"family": "bimodal_synthetic", "scenario_name": "bimodal_intent_synthetic", "seed": seed, "cfg": cfg, "sim": sim})

    for p_name in sorted(list(SCENARIO_REGISTRY.keys())):
        for s_idx in range(1, 11):
            seed = 26000 + s_idx
            cfg = get_scenario(p_name, seed=seed)
            sim = run_simulation(cfg)
            simulations.append({"family": "preset", "scenario_name": p_name, "seed": seed, "cfg": cfg, "sim": sim})

    return simulations

def execute_evaluation():
    print("=" * 80)
    print("STEP 4D.5: ALIGNED BENCHMARK EVALUATION & ECONOMIC REGRET AUDIT")
    print("=" * 80)

    print("Building paired dataset (190 runs, 450 ads)...")
    simulations = build_dataset()
    print(f"Dataset instantiated: {len(simulations)} runs.")

    policies = {
        "PROD_P10": {
            "name": "Production Policy (ci=0.90, N=20, decision_thresh=0.10)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60, min_mature_leads=30),
            "decision_policy": DecisionPolicy(low_qualification_upper_bound=0.10, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60, min_mature_leads_for_reachability=30),
        },
        "PROD_P15": {
            "name": "Production Policy on 0.15 Hurdle (ci=0.90, N=20, decision_thresh=0.15)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60, min_mature_leads=30),
            "decision_policy": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60, min_mature_leads_for_reachability=30),
        },
        "CONFIG_A_P15": {
            "name": "Step 4D Baseline Config A (ci=0.80, N=12, decision_thresh=0.15)",
            "estimator_cfg": EstimatorConfig(ci_level=0.80, min_mature_contacts=12, min_maturity_fraction=0.50, min_mature_leads=30),
            "decision_policy": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=12, min_maturity_fraction=0.50, min_mature_leads_for_reachability=30),
        },
    }

    scoring_hurdles = [0.10, 0.15]
    regret_vql_grid = [50.0, 75.0, 100.0, 150.0, 200.0, 300.0, 400.0, 500.0, 750.0, 1000.0, 1500.0, 2000.0]

    master_results = {}

    for pol_key, pol_info in policies.items():
        print(f"\n--- Running Policy: {pol_info['name']} ---")
        est_config = pol_info["estimator_cfg"]
        dec_policy = pol_info["decision_policy"]

        # Run sequential policy simulation once per policy
        # Store all ad-level actions and outcomes
        policy_ad_runs = []

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
                        }

            # Compile ad-level data for this run
            run_ad_list = []
            for ad in sim.advertisements:
                gt = gt_by_ad[ad.id]
                q_true = float(np.mean(gt.true_intent_by_day))
                p_day = paused_day[ad.id]

                # Full 28-day reference values
                all_ad_quals = [l for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id]
                full_ql = len(all_ad_quals)
                full_spend = float(ad.spend)

                # Day 14 reference (earliest possible checkpoint for oracle poor-ad pause)
                t_d14 = epoch + np.timedelta64(14, "D").astype("timedelta64[s]").item()
                d14_spend = round(ad.spend * (14 / horizon), 2)
                d14_ql_m1 = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_d14 and l.id in qual_by_lead_id)

                if p_day is not None:
                    ad_spend = round(ad.spend * (p_day / horizon), 2)
                    t_p = epoch + np.timedelta64(p_day, "D").astype("timedelta64[s]").item()
                    # Metric 1: Pipeline harvest (leads created before pause)
                    m1_ql = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_p and l.id in qual_by_lead_id)
                    # Metric 2: Strictly resolved at or before pause
                    m2_ql = sum(1 for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id and qual_by_lead_id[l.id].resolved_at <= t_p)
                    # Foregone / lost leads from pause day to Day 28
                    m1_lost_ql = full_ql - m1_ql
                    m2_lost_ql = full_ql - m2_ql
                else:
                    ad_spend = full_spend
                    m1_ql = full_ql
                    m2_ql = full_ql
                    m1_lost_ql = 0
                    m2_lost_ql = 0

                run_ad_list.append({
                    "family": family,
                    "scenario_name": sc_name,
                    "seed": seed,
                    "ad_id": ad.id,
                    "creative_id": ad.creative_id,
                    "q_true": q_true,
                    "paused_day": p_day,
                    "spend": ad_spend,
                    "full_spend": full_spend,
                    "d14_spend": d14_spend,
                    "m1_ql": m1_ql,
                    "m2_ql": m2_ql,
                    "full_ql": full_ql,
                    "d14_ql_m1": d14_ql_m1,
                    "m1_lost_ql": m1_lost_ql,
                    "m2_lost_ql": m2_lost_ql,
                    "pause_details": pause_details[ad.id],
                })

            policy_ad_runs.append({
                "family": family,
                "scenario_name": sc_name,
                "seed": seed,
                "ads": run_ad_list,
            })

        # Now score this policy's identical execution under BOTH scoring hurdles
        policy_scoring_views = {}

        for h in scoring_hurdles:
            h_key = f"hurdle_{int(round(h*100)):02d}"

            total_ads = 0
            good_ads = 0
            poor_ads = 0
            false_pauses = 0
            missed_poor = 0

            spend_on_poor = 0.0
            spend_before_pause_poor = 0.0
            spend_on_missed_poor = 0.0

            total_spend = 0.0
            total_m1_ql = 0
            total_m2_ql = 0

            lost_ql_m1 = 0
            lost_ql_m2 = 0

            pause_days = []

            # Regret tracking
            # Good ads regret: V_QL * lost_ql - saved_spend
            # Poor ads regret: excess_spend - V_QL * excess_ql (relative to Day 14 oracle)
            good_lost_ql_sum = 0
            good_saved_spend_sum = 0.0
            poor_excess_spend_sum = 0.0
            poor_excess_ql_sum = 0

            per_run_records = []

            for run in policy_ad_runs:
                r_good = 0
                r_poor = 0
                r_fp = 0
                r_missed = 0
                r_spend = 0.0
                r_poor_spend = 0.0
                r_m1_ql = 0
                r_m2_ql = 0
                r_lost_ql = 0

                for ad in run["ads"]:
                    total_ads += 1
                    q_true = ad["q_true"]
                    is_good = (q_true >= h)
                    is_poor = (q_true < h)

                    p_day = ad["paused_day"]
                    ad_spend = ad["spend"]
                    m1_ql = ad["m1_ql"]
                    m2_ql = ad["m2_ql"]

                    total_spend += ad_spend
                    total_m1_ql += m1_ql
                    total_m2_ql += m2_ql
                    r_spend += ad_spend
                    r_m1_ql += m1_ql
                    r_m2_ql += m2_ql

                    if is_good:
                        good_ads += 1
                        r_good += 1
                        if p_day is not None:
                            false_pauses += 1
                            r_fp += 1
                            pause_days.append(p_day)
                            lost_ql_m1 += ad["m1_lost_ql"]
                            lost_ql_m2 += ad["m2_lost_ql"]
                            r_lost_ql += ad["m1_lost_ql"]

                            # Regret components for good ad
                            saved_sp = ad["full_spend"] - ad_spend
                            good_saved_spend_sum += saved_sp
                            good_lost_ql_sum += ad["m1_lost_ql"]

                    elif is_poor:
                        poor_ads += 1
                        r_poor += 1
                        spend_on_poor += ad_spend
                        r_poor_spend += ad_spend

                        if p_day is not None:
                            pause_days.append(p_day)
                            spend_before_pause_poor += ad_spend
                            # Relative to Day 14 oracle
                            excess_sp = max(0.0, ad_spend - ad["d14_spend"])
                            excess_ql = max(0, m1_ql - ad["d14_ql_m1"])
                        else:
                            missed_poor += 1
                            r_missed += 1
                            spend_on_missed_poor += ad_spend
                            excess_sp = max(0.0, ad["full_spend"] - ad["d14_spend"])
                            excess_ql = max(0, m1_ql - ad["d14_ql_m1"])

                        poor_excess_spend_sum += excess_sp
                        poor_excess_ql_sum += excess_ql

                per_run_records.append({
                    "family": run["family"],
                    "scenario_name": run["scenario_name"],
                    "seed": run["seed"],
                    "good_ads": r_good,
                    "poor_ads": r_poor,
                    "false_pauses": r_fp,
                    "missed_poor": r_missed,
                    "fp_rate": (r_fp / r_good) if r_good > 0 else 0.0,
                    "missed_rate": (r_missed / r_poor) if r_poor > 0 else 0.0,
                    "total_spend": round(r_spend, 2),
                    "poor_spend": round(r_poor_spend, 2),
                    "m1_ql": r_m1_ql,
                    "m2_ql": r_m2_ql,
                    "lost_ql": r_lost_ql,
                })

            fp_rate, fp_low, fp_high = wilson_score_ci(false_pauses, good_ads)
            mp_rate, mp_low, mp_high = wilson_score_ci(missed_poor, poor_ads)

            cpql_m1 = round(total_spend / total_m1_ql, 2) if total_m1_ql > 0 else None
            cpql_m2 = round(total_spend / total_m2_ql, 2) if total_m2_ql > 0 else None

            # Distribution statistics across the 190 runs
            run_fp_rates = [r["fp_rate"] for r in per_run_records if r["good_ads"] > 0]
            run_mp_rates = [r["missed_rate"] for r in per_run_records if r["poor_ads"] > 0]
            run_spends = [r["total_spend"] for r in per_run_records]
            run_qls = [r["m1_ql"] for r in per_run_records]

            # Linear Regret Model:
            # Regret(V_QL) = A + B * V_QL
            # A = Poor Excess Spend - Good Saved Spend
            # B = Good Lost QL - Poor Excess QL
            regret_A = poor_excess_spend_sum - good_saved_spend_sum
            regret_B = good_lost_ql_sum - poor_excess_ql_sum

            regret_evaluations = {}
            for vql in regret_vql_grid:
                regret_val = regret_A + (regret_B * vql)
                regret_evaluations[str(int(vql))] = round(regret_val, 2)

            pause_day_counts = {str(d): pause_days.count(d) for d in CHECKPOINTS}
            mean_pause_day = float(np.mean(pause_days)) if pause_days else None

            policy_scoring_views[h_key] = {
                "hurdle": h,
                "total_ads": total_ads,
                "good_ads": good_ads,
                "poor_ads": poor_ads,
                "false_pauses": false_pauses,
                "false_pause_rate": round(fp_rate, 4),
                "false_pause_ci95": [round(fp_low, 4), round(fp_high, 4)],
                "missed_poor": missed_poor,
                "missed_poor_rate": round(mp_rate, 4),
                "missed_poor_ci95": [round(mp_low, 4), round(mp_high, 4)],
                "spend_on_poor": round(spend_on_poor, 2),
                "spend_before_pause_poor": round(spend_before_pause_poor, 2),
                "spend_on_missed_poor": round(spend_on_missed_poor, 2),
                "total_spend": round(total_spend, 2),
                "total_m1_ql": total_m1_ql,
                "total_m2_ql": total_m2_ql,
                "lost_ql_m1": lost_ql_m1,
                "lost_ql_m2": lost_ql_m2,
                "cpql_m1": cpql_m1,
                "cpql_m2": cpql_m2,
                "mean_pause_day": round(mean_pause_day, 2) if mean_pause_day else None,
                "pause_day_counts": pause_day_counts,
                "regret_formula": {
                    "formula": f"Regret(V_QL) = {regret_A:,.2f} + ({regret_B:d} * V_QL)",
                    "A_spend_waste_component": round(regret_A, 2),
                    "B_lost_lead_component": regret_B,
                    "poor_excess_spend": round(poor_excess_spend_sum, 2),
                    "good_saved_spend": round(good_saved_spend_sum, 2),
                    "good_lost_ql": good_lost_ql_sum,
                    "poor_excess_ql": poor_excess_ql_sum,
                },
                "regret_grid": regret_evaluations,
                "run_distributions": {
                    "fp_rate_mean": round(float(np.mean(run_fp_rates)), 4) if run_fp_rates else 0.0,
                    "fp_rate_std": round(float(np.std(run_fp_rates)), 4) if run_fp_rates else 0.0,
                    "fp_rate_median": round(float(np.median(run_fp_rates)), 4) if run_fp_rates else 0.0,
                    "mp_rate_mean": round(float(np.mean(run_mp_rates)), 4) if run_mp_rates else 0.0,
                    "mp_rate_std": round(float(np.std(run_mp_rates)), 4) if run_mp_rates else 0.0,
                    "mp_rate_median": round(float(np.median(run_mp_rates)), 4) if run_mp_rates else 0.0,
                    "spend_per_run_mean": round(float(np.mean(run_spends)), 2),
                    "spend_per_run_std": round(float(np.std(run_spends)), 2),
                    "ql_per_run_mean": round(float(np.mean(run_qls)), 2),
                    "ql_per_run_std": round(float(np.std(run_qls)), 2),
                },
                "per_run_records": per_run_records,
            }

        master_results[pol_key] = {
            "policy_name": pol_info["name"],
            "scoring_views": policy_scoring_views,
        }

    # Save complete evaluation output
    out_file = "scratch/step_4d5_aligned_evaluation.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(master_results, f, indent=2)
    print(f"\nSaved aligned evaluation results to {out_file}")

    # Compute Crossover Points for Regret between Policies
    print("\n" + "=" * 80)
    print("REGRET CROSSOVER ANALYSIS (V_QL* where Regret(Pol_1) == Regret(Pol_2))")
    print("=" * 80)
    for h_key in ["hurdle_10", "hurdle_15"]:
        h_val = 0.10 if h_key == "hurdle_10" else 0.15
        print(f"\nScoring Hurdle = {h_val:.2f} ({h_key}):")
        p1 = master_results["PROD_P10"]["scoring_views"][h_key]["regret_formula"]
        p2 = master_results["PROD_P15"]["scoring_views"][h_key]["regret_formula"]
        p3 = master_results["CONFIG_A_P15"]["scoring_views"][h_key]["regret_formula"]

        # PROD_P10 vs PROD_P15:
        # A1 + B1 * V = A2 + B2 * V => V* = (A1 - A2) / (B2 - B1)
        dA_12 = p1["A_spend_waste_component"] - p2["A_spend_waste_component"]
        dB_12 = p2["B_lost_lead_component"] - p1["B_lost_lead_component"]
        v_star_12 = (dA_12 / dB_12) if dB_12 != 0 else None
        print(f"  PROD_P10 vs PROD_P15 Crossover: V_QL* = Rs {v_star_12:,.2f}" if v_star_12 else "  No crossover")

        # PROD_P10 vs CONFIG_A_P15:
        dA_13 = p1["A_spend_waste_component"] - p3["A_spend_waste_component"]
        dB_13 = p3["B_lost_lead_component"] - p1["B_lost_lead_component"]
        v_star_13 = (dA_13 / dB_13) if dB_13 != 0 else None
        print(f"  PROD_P10 vs CONFIG_A_P15 Crossover: V_QL* = Rs {v_star_13:,.2f}" if v_star_13 else "  No crossover")

if __name__ == "__main__":
    execute_evaluation()
