"""
Step 4D.8: Economic Viability Evaluator vs Production Heuristic Evaluation Runner

Evaluates on the canonical 190 paired simulation runs (450 total ads):
- 50 continuous intent runs (seeds 22000-22049)
- 50 bimodal synthetic runs (seeds 24000-24049)
- 90 preset runs (10 seeds x 9 presets, seeds 26001-26010)

Policies Evaluated:
1. PROD_HEURISTIC_P10: Production heuristic policy (ci=0.90, N=20, qual_thresh=0.10)
2. PROD_HEURISTIC_P15: Production heuristic policy on 15% hurdle (ci=0.90, N=20, qual_thresh=0.15)
3. ECON_V300: Economic Evaluator (lead_value = Rs 300)
4. ECON_V600: Economic Evaluator (lead_value = Rs 600)
5. ECON_V1200: Economic Evaluator (lead_value = Rs 1,200)
6. ECON_SEGMENTED: Economic Evaluator (Tier 1/Search = Rs 1,500, Tier 2/Social = Rs 400)

Strictly isolated: Evaluator NEVER accesses ground truth during decisions.
Ground truth is used strictly for post-hoc scoring.
"""

import json
import math
import os
import sys
from typing import Dict, Any, List, Tuple

import numpy as np
import scipy.stats as stats

# Ensure repo root and backend are on sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
backend_path = os.path.join(repo_root, "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from benchmark.sequential import is_pause
from decision_engine.engine import DecisionPolicy, evaluate_campaign, DecisionAction
from domain.enums import QualificationResult
from estimator.estimator import EstimatorConfig, compute_campaign_estimates
from simulator.engine import run_simulation
from simulator.scenarios import AdConfig, ScenarioConfig, get_scenario, SCENARIO_REGISTRY
from scratch.economic_evaluator import (
    EconomicAction,
    EconomicParameters,
    evaluate_ad_economic_viability,
)

CHECKPOINTS = [3, 7, 14, 21]

def wilson_score_ci(k: int, n: int, conf: float = 0.95) -> Tuple[float, float, float]:
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = k / n
    z = stats.norm.ppf(1.0 - (1.0 - conf) / 2.0)
    denom = 1.0 + (z**2) / n
    centre = (p + (z**2) / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))) / denom
    return float(p), float(max(0.0, centre - spread)), float(min(1.0, centre + spread))

def generate_continuous_scenario(seed: int, n_ads: int = 3) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        true_intent = round(float(rng.uniform(0.05, 0.25)), 4)
        true_reach = round(float(rng.uniform(0.40, 0.70)), 4)
        # Randomly vary spend to introduce high-CPL and low-CPL ads
        # e.g., impressions from 50k to 150k, clicks from 1k to 3k
        clicks = int(rng.integers(1200, 3500))
        spend = float(rng.choice([3000.0, 5000.0, 7500.0]))
        ads.append(
            AdConfig(
                creative_id=f"cr-cont-{seed}-{i}",
                spend=spend,
                impressions=100000,
                clicks=clicks,
                true_reachability=true_reach,
                true_intent=true_intent,
                fatigue_enabled=False,
                label="unlabelled",
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
        spend = float(rng.choice([4000.0, 5000.0, 6000.0]))
        ads.append(
            AdConfig(
                creative_id=f"cr-bimodal-{seed}-{i}",
                spend=spend,
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

def run_evaluation_suite():
    print("=" * 80)
    print("STEP 4D.8: ECONOMIC VIABILITY EVALUATOR PROTOTYPE VS PRODUCTION HEURISTIC")
    print("=" * 80)

    print("Building paired simulations (190 runs, 450 ads)...")
    simulations = build_dataset()
    print(f"Paired simulations loaded: {len(simulations)} runs.")

    # Base estimator configuration (production 90% CI, min 20 mature contacts)
    base_est_cfg = EstimatorConfig(
        ci_level=0.90,
        min_mature_contacts=20,
        min_maturity_fraction=0.60,
        min_mature_leads=30,
    )

    # Segment valuation function for heterogeneous lead evaluation
    def segmented_lead_val(tier: str) -> float:
        # Tier 1 / high-intent = Rs 1,500; Tier 2 / broad social = Rs 400
        return 1500.0 if tier == "tier1" else 400.0

    configs = {
        "PROD_HEURISTIC_P10": {
            "name": "Production Heuristic (threshold=0.10, ci=0.90)",
            "type": "heuristic",
            "policy": DecisionPolicy(low_qualification_upper_bound=0.10, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60, min_mature_leads_for_reachability=30),
        },
        "PROD_HEURISTIC_P15": {
            "name": "Production Heuristic on 15% Hurdle (threshold=0.15, ci=0.90)",
            "type": "heuristic",
            "policy": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60, min_mature_leads_for_reachability=30),
        },
        "ECON_V300": {
            "name": "Economic Evaluator (V_QL = Rs 300)",
            "type": "economic",
            "params": EconomicParameters(lead_value=300.0, min_mature_contacts=20, min_maturity_fraction=0.60, confidence_level=0.90),
        },
        "ECON_V600": {
            "name": "Economic Evaluator (V_QL = Rs 600)",
            "type": "economic",
            "params": EconomicParameters(lead_value=600.0, min_mature_contacts=20, min_maturity_fraction=0.60, confidence_level=0.90),
        },
        "ECON_V1200": {
            "name": "Economic Evaluator (V_QL = Rs 1,200)",
            "type": "economic",
            "params": EconomicParameters(lead_value=1200.0, min_mature_contacts=20, min_maturity_fraction=0.60, confidence_level=0.90),
        },
        "ECON_SEGMENTED": {
            "name": "Economic Evaluator (Segmented: Tier 1 = Rs 1,500, Tier 2 = Rs 400)",
            "type": "economic",
            "params": EconomicParameters(lead_value=600.0, min_mature_contacts=20, min_maturity_fraction=0.60, confidence_level=0.90, segment_value_fn=segmented_lead_val),
        },
    }

    eval_results = {}
    all_policy_ad_records = {}

    for c_key, c_info in configs.items():
        print(f"Evaluating {c_info['name']}...")
        is_econ = (c_info["type"] == "economic")
        pol = c_info.get("policy")
        econ_params = c_info.get("params")

        ad_records = []
        run_profit_list = []

        for item in simulations:
            cfg = item["cfg"]
            sim = item["sim"]
            seed = item["seed"]
            family = item["family"]
            sc_name = item["scenario_name"]

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
                    config=base_est_cfg,
                    seed=seed,
                )

                if is_econ:
                    # Economic Evaluator
                    for snap in snaps:
                        ad_id = snap.advertisement_id
                        cur_sp = accrued_spends[ad_id]
                        # Determine tier: preset ads with high intent or continuous index 0 = tier1, others = tier2
                        tier = "tier1" if ("excellent" in ad_id or "-0" in ad_id) else "tier2"
                        res = evaluate_ad_economic_viability(
                            snapshot=snap,
                            cumulative_spend=cur_sp,
                            current_day=float(cp_day),
                            params=econ_params,
                            campaign_tier=tier,
                        )
                        if res.action == EconomicAction.PAUSE and paused_day[ad_id] is None:
                            paused_day[ad_id] = cp_day
                else:
                    # Heuristic Engine
                    decs = evaluate_campaign(
                        snapshots=snaps,
                        ad_spends={ad.id: accrued_spends[ad.id] for ad in active_ads},
                        policy=pol,
                    )
                    for dec in decs:
                        if is_pause(dec.action) and paused_day[dec.advertisement_id] is None:
                            paused_day[dec.advertisement_id] = cp_day

            # Collect ad outcomes
            run_spend = 0.0
            run_ql = 0
            for ad in sim.advertisements:
                gt = gt_by_ad[ad.id]
                q_true = float(np.mean(gt.true_intent_by_day))
                r_true = gt.true_reachability
                p_day = paused_day[ad.id]

                full_spend = float(ad.spend)
                all_quals = [l for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id]
                full_ql = len(all_quals)

                if p_day is not None:
                    ad_spend = round(ad.spend * (p_day / horizon), 2)
                    t_p = epoch + np.timedelta64(p_day, "D").astype("timedelta64[s]").item()
                    m1_ql = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_p and l.id in qual_by_lead_id)
                else:
                    ad_spend = full_spend
                    m1_ql = full_ql

                # True economic CPQL of this ad over full run
                expected_total_ql = max(1.0, len(leads_by_ad[ad.id]) * r_true * q_true)
                true_cpql = full_spend / expected_total_ql

                tier = "tier1" if ("excellent" in ad.id or "-0" in ad.id) else "tier2"

                run_spend += ad_spend
                run_ql += m1_ql

                ad_records.append({
                    "family": family,
                    "scenario_name": sc_name,
                    "seed": seed,
                    "ad_id": ad.id,
                    "q_true": q_true,
                    "r_true": r_true,
                    "true_cpql": true_cpql,
                    "spend": ad_spend,
                    "full_spend": full_spend,
                    "m1_ql": m1_ql,
                    "full_ql": full_ql,
                    "paused_day": p_day,
                    "tier": tier,
                })

        # Calculate metrics under multiple business valuations (V_QL in [300, 600, 1200, segmented])
        valuations = [300.0, 600.0, 1200.0]
        val_metrics = {}

        for v in valuations:
            tot_spend = sum(a["spend"] for a in ad_records)
            tot_ql = sum(a["m1_ql"] for a in ad_records)
            tot_profit = (v * tot_ql) - tot_spend

            # Ground truth economic viability under valuation V:
            # An ad is genuinely economically viable iff its true CPQL <= V
            viable_ads = [a for a in ad_records if a["true_cpql"] <= v]
            unviable_ads = [a for a in ad_records if a["true_cpql"] > v]

            # False pause of economically viable ad:
            false_pauses_econ = [a for a in viable_ads if a["paused_day"] is not None]
            fp_rate, fp_low, fp_high = wilson_score_ci(len(false_pauses_econ), len(viable_ads))

            # Continued spend on unviable ad (missed unviable):
            missed_unviable = [a for a in unviable_ads if a["paused_day"] is None]
            mp_rate, mp_low, mp_high = wilson_score_ci(len(missed_unviable), len(unviable_ads))

            spend_on_unviable = sum(a["spend"] for a in unviable_ads)
            spend_on_missed_unviable = sum(a["spend"] for a in missed_unviable)

            val_metrics[f"V_{int(v)}"] = {
                "lead_value": v,
                "net_contribution_profit": round(tot_profit, 2),
                "n_viable": len(viable_ads),
                "n_unviable": len(unviable_ads),
                "false_pauses_econ": len(false_pauses_econ),
                "false_pause_rate": round(fp_rate, 4),
                "false_pause_ci95": [round(fp_low, 4), round(fp_high, 4)],
                "missed_unviable": len(missed_unviable),
                "missed_unviable_rate": round(mp_rate, 4),
                "missed_unviable_ci95": [round(mp_low, 4), round(mp_high, 4)],
                "spend_on_unviable": round(spend_on_unviable, 2),
                "spend_on_missed_unviable": round(spend_on_missed_unviable, 2),
            }

        # Segmented profit
        tot_spend = sum(a["spend"] for a in ad_records)
        seg_ql_rev = sum((1500.0 if a["tier"] == "tier1" else 400.0) * a["m1_ql"] for a in ad_records)
        seg_profit = seg_ql_rev - tot_spend

        total_paused = len([a for a in ad_records if a["paused_day"] is not None])
        pause_days = [a["paused_day"] for a in ad_records if a["paused_day"] is not None]
        mean_pause_day = float(np.mean(pause_days)) if pause_days else None
        pause_counts = {str(d): pause_days.count(d) for d in CHECKPOINTS}

        cpql = round(tot_spend / sum(a["m1_ql"] for a in ad_records), 2)

        eval_results[c_key] = {
            "name": c_info["name"],
            "type": c_info["type"],
            "total_ads": len(ad_records),
            "total_spend": round(tot_spend, 2),
            "total_ql": sum(a["m1_ql"] for a in ad_records),
            "cpql": cpql,
            "paused_count": total_paused,
            "mean_pause_day": round(mean_pause_day, 2) if mean_pause_day else None,
            "pause_counts": pause_counts,
            "valuation_metrics": val_metrics,
            "segmented_profit": round(seg_profit, 2),
        }
        all_policy_ad_records[c_key] = ad_records

    # Paired Profit Differences against PROD_HEURISTIC_P10 across the 450 ads / 190 simulation runs
    print("\nComputing paired profit differences vs PROD_HEURISTIC_P10...")
    baseline_ads = all_policy_ad_records["PROD_HEURISTIC_P10"]
    baseline_ad_dict = {a["ad_id"]: a for a in baseline_ads}

    paired_analysis = {}
    for c_key in configs.keys():
        if c_key == "PROD_HEURISTIC_P10":
            continue
        c_ads = all_policy_ad_records[c_key]
        c_ad_dict = {a["ad_id"]: a for a in c_ads}

        paired_analysis[c_key] = {}
        for val_name, v_val in [("V_300", 300.0), ("V_600", 600.0), ("V_1200", 1200.0), ("Segmented", None)]:
            deltas = []
            for ad_id, base_a in baseline_ad_dict.items():
                cand_a = c_ad_dict[ad_id]
                if v_val is not None:
                    base_prof = (v_val * base_a["m1_ql"]) - base_a["spend"]
                    cand_prof = (v_val * cand_a["m1_ql"]) - cand_a["spend"]
                else:
                    v_base = 1500.0 if base_a["tier"] == "tier1" else 400.0
                    base_prof = (v_base * base_a["m1_ql"]) - base_a["spend"]
                    v_cand = 1500.0 if cand_a["tier"] == "tier1" else 400.0
                    cand_prof = (v_cand * cand_a["m1_ql"]) - cand_a["spend"]
                deltas.append(cand_prof - base_prof)

            mean_d = float(np.mean(deltas))
            std_d = float(np.std(deltas, ddof=1))
            n = len(deltas)
            se_d = std_d / math.sqrt(n)
            ci_low = mean_d - 1.96 * se_d
            ci_high = mean_d + 1.96 * se_d
            t_stat = mean_d / se_d if se_d > 1e-9 else 0.0
            p_val = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=n - 1)))

            paired_analysis[c_key][val_name] = {
                "total_delta_profit": float(np.sum(deltas)),
                "mean_delta_profit_per_ad": round(mean_d, 2),
                "se_delta_profit": round(se_d, 2),
                "ci95_delta_profit_per_ad": [round(ci_low, 2), round(ci_high, 2)],
                "t_stat": round(t_stat, 3),
                "p_value": round(p_val, 4),
            }

    eval_results["paired_comparisons_vs_prod_p10"] = paired_analysis

    out_file = "scratch/step_4d8_economic_prototype_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=2)

    print(f"\nSaved prototype evaluation results to {out_file}")

    print("\n" + "=" * 90)
    print("PROTOTYPE RESULTS SUMMARY (Net Contribution Profit at V_QL = Rs 300, 600, 1,200 & Segmented)")
    print("=" * 90)
    for c_key, res in eval_results.items():
        if c_key == "paired_comparisons_vs_prod_p10":
            continue
        v3 = res["valuation_metrics"]["V_300"]["net_contribution_profit"]
        v6 = res["valuation_metrics"]["V_600"]["net_contribution_profit"]
        v12 = res["valuation_metrics"]["V_1200"]["net_contribution_profit"]
        seg = res["segmented_profit"]
        print(f"\n--- {res['name']} ({c_key}) ---")
        print(f"  Total Spend: Rs {res['total_spend']:,.2f} | Total QL: {res['total_ql']} | CPQL: Rs {res['cpql']:.2f}")
        print(f"  Total Pauses: {res['paused_count']} (Mean Pause Day: {res['mean_pause_day']}) | Counts: {res['pause_counts']}")
        print(f"  Net Profit @ V=Rs 300: Rs {v3:,.2f}")
        print(f"  Net Profit @ V=Rs 600: Rs {v6:,.2f} (Econ False Pauses: {res['valuation_metrics']['V_600']['false_pauses_econ']}/{res['valuation_metrics']['V_600']['n_viable']}, Missed Unviable: {res['valuation_metrics']['V_600']['missed_unviable']}/{res['valuation_metrics']['V_600']['n_unviable']})")
        print(f"  Net Profit @ V=Rs 1200: Rs {v12:,.2f}")
        print(f"  Net Profit @ Segmented: Rs {seg:,.2f}")

if __name__ == "__main__":
    run_evaluation_suite()
