"""
Step 4D.4.1: Counterfactual Evaluation of Unmodified Production Policy vs Candidate Boundary Rules

Evaluates:
1. PROD_UNMODIFIED_T10: Production Defaults (ci=0.90, N=20, thresh=0.10)
2. PROD_LITERAL_ABSTENTION_T10: Literal Proposal Abstention (|mean - thresh| <= 0.015, thresh=0.10)
3. PROD_CORRECTED_ABSTENTION_T10: Corrected Boundary Abstention (|ci_high - thresh| <= 0.015, N<40, thresh=0.10)
4. BENCH_PROD_T15: Production Policy on Benchmark Hurdle (ci=0.90, N=20, thresh=0.15)
5. BENCH_CORRECTED_ABSTENTION_T15: Corrected Boundary on Benchmark Hurdle (thresh=0.15)
6. BENCH_CONFIG_A_CI80_T15: Step 4D Experimental Baseline (ci=0.80, N=12, thresh=0.15)

Deterministic paired evaluation on 190 simulation runs (450 total ads):
- 50 continuous intent runs (seeds 22000-22049)
- 50 bimodal synthetic runs (seeds 24000-24049)
- 90 preset runs (10 seeds x 9 presets, seeds 26001-26010)
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

HURDLE_SIM = 0.15
CHECKPOINTS = [3, 7, 14, 21]

def generate_continuous_scenario(seed: int, n_ads: int = 3, hurdle: float = 0.15) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        true_intent = round(float(rng.uniform(0.05, 0.25)), 4)
        true_reach = round(float(rng.uniform(0.40, 0.70)), 4)
        label = "good" if true_intent >= hurdle else "bad"
        ads.append(
            AdConfig(
                creative_id=f"cr-cont-{seed}-{i}",
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
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[ads],
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
        leads_per_day_per_ad=5.0,
    )

def build_dataset() -> List[Dict[str, Any]]:
    simulations = []
    # 50 Continuous runs
    for seed in range(22000, 22050):
        cfg = generate_continuous_scenario(seed=seed, n_ads=3, hurdle=HURDLE_SIM)
        sim = run_simulation(cfg)
        simulations.append({"family": "continuous", "scenario_name": "continuous_intent", "seed": seed, "cfg": cfg, "sim": sim})

    # 50 Bimodal Synthetic runs
    for seed in range(24000, 24050):
        cfg = generate_bimodal_scenario(seed=seed, n_ads=3)
        sim = run_simulation(cfg)
        simulations.append({"family": "bimodal_synthetic", "scenario_name": "bimodal_intent_synthetic", "seed": seed, "cfg": cfg, "sim": sim})

    # 90 Preset runs (10 seeds each for all 9 presets)
    for p_name in sorted(list(SCENARIO_REGISTRY.keys())):
        for s_idx in range(1, 11):
            seed = 26000 + s_idx
            cfg = get_scenario(p_name, seed=seed)
            sim = run_simulation(cfg)
            simulations.append({"family": "preset", "scenario_name": p_name, "seed": seed, "cfg": cfg, "sim": sim})

    return simulations

def run_evaluation():
    print("Building dataset...")
    simulations = build_dataset()
    print(f"Dataset ready: {len(simulations)} runs.")

    configs = {
        "1_PROD_UNMODIFIED_T10": {
            "name": "Production Default (ci=0.90, N=20, thresh=0.10)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60),
            "policy": DecisionPolicy(low_qualification_upper_bound=0.10, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60),
            "abstention": "none",
        },
        "2_PROD_LITERAL_ABSTENTION_T10": {
            "name": "Literal Proposal Abstention (|mean - thresh| <= 0.015, thresh=0.10)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60),
            "policy": DecisionPolicy(low_qualification_upper_bound=0.10, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60),
            "abstention": "literal_proposal",
        },
        "3_PROD_CORRECTED_ABSTENTION_T10": {
            "name": "Corrected Boundary Abstention (|ci_high - thresh| <= 0.015, N<40, thresh=0.10)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60),
            "policy": DecisionPolicy(low_qualification_upper_bound=0.10, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60),
            "abstention": "corrected_boundary",
        },
        "4_BENCH_PROD_CI90_T15": {
            "name": "Production Policy on 0.15 Hurdle (ci=0.90, N=20, thresh=0.15)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60),
            "policy": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60),
            "abstention": "none",
        },
        "5_BENCH_CORRECTED_ABSTENTION_T15": {
            "name": "Corrected Boundary on 0.15 Hurdle (|ci_high - 0.15| <= 0.015, N<40, thresh=0.15)",
            "estimator_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60),
            "policy": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60),
            "abstention": "corrected_boundary",
        },
        "6_BENCH_CONFIG_A_CI80_T15": {
            "name": "Step 4D Baseline Config A (ci=0.80, N=12, thresh=0.15)",
            "estimator_cfg": EstimatorConfig(ci_level=0.80, min_mature_contacts=12, min_maturity_fraction=0.50),
            "policy": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=12, min_maturity_fraction=0.50),
            "abstention": "none",
        },
    }

    results = {}

    for c_key, c_info in configs.items():
        print(f"Evaluating {c_info['name']}...")
        est_config = c_info["estimator_cfg"]
        dec_policy = c_info["policy"]
        abst_mode = c_info["abstention"]

        total_ads = 0
        good_ads_015 = 0
        poor_ads_015 = 0
        good_ads_010 = 0
        poor_ads_010 = 0

        false_pauses_015 = 0
        missed_poor_015 = 0
        false_pauses_010 = 0
        missed_poor_010 = 0

        pause_days = []
        spend_on_poor_015 = 0.0
        spend_on_poor_010 = 0.0
        total_spend = 0.0
        total_ql = 0

        intercepted_count = 0

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

                    # Check abstention
                    if is_pause(action) and "sitting entirely below threshold" in dec.reason:
                        if abst_mode == "literal_proposal":
                            if abs(snap.qualification_mean - dec_policy.low_qualification_upper_bound) <= 0.015:
                                action = DecisionAction.COLLECT_MORE_DATA
                                intercepted_count += 1
                        elif abst_mode == "corrected_boundary":
                            if abs(snap.qualification_ci_high - dec_policy.low_qualification_upper_bound) <= 0.015 and snap.n_mature_contacts < 40:
                                action = DecisionAction.COLLECT_MORE_DATA
                                intercepted_count += 1

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

            for ad in sim.advertisements:
                total_ads += 1
                gt = gt_by_ad[ad.id]
                q_true = float(np.mean(gt.true_intent_by_day))
                is_good_015 = (gt.label == "good")
                is_poor_015 = (gt.label == "bad")

                is_good_010 = (q_true >= 0.10)
                is_poor_010 = (q_true < 0.10)

                if is_good_015:
                    good_ads_015 += 1
                else:
                    poor_ads_015 += 1

                if is_good_010:
                    good_ads_010 += 1
                else:
                    poor_ads_010 += 1

                p_day = paused_day[ad.id]
                all_ad_quals = [l for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id]
                full_ql = len(all_ad_quals)

                if p_day is not None:
                    ad_spend = round(ad.spend * (p_day / horizon), 2)
                    t_p = epoch + np.timedelta64(p_day, "D").astype("timedelta64[s]").item()
                    ad_ql = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_p and l.id in qual_by_lead_id)
                    pause_days.append(p_day)
                    if is_good_015:
                        false_pauses_015 += 1
                    if is_good_010:
                        false_pauses_010 += 1
                else:
                    ad_spend = float(ad.spend)
                    ad_ql = full_ql
                    if is_poor_015:
                        missed_poor_015 += 1
                    if is_poor_010:
                        missed_poor_010 += 1

                if is_poor_015:
                    spend_on_poor_015 += ad_spend
                if is_poor_010:
                    spend_on_poor_010 += ad_spend

                total_spend += ad_spend
                total_ql += ad_ql

        mean_pause_day = float(np.mean(pause_days)) if pause_days else None
        cpql = total_spend / total_ql if total_ql > 0 else float("inf")

        fp_rate_015 = false_pauses_015 / good_ads_015 if good_ads_015 > 0 else 0.0
        missed_rate_015 = missed_poor_015 / poor_ads_015 if poor_ads_015 > 0 else 0.0
        fp_rate_010 = false_pauses_010 / good_ads_010 if good_ads_010 > 0 else 0.0
        missed_rate_010 = missed_poor_010 / poor_ads_010 if poor_ads_010 > 0 else 0.0

        pause_day_counts = {str(d): pause_days.count(d) for d in CHECKPOINTS}

        results[c_key] = {
            "name": c_info["name"],
            "total_ads": total_ads,
            "intercepted_count": intercepted_count,
            "good_ads_015": good_ads_015,
            "poor_ads_015": poor_ads_015,
            "false_pauses_015": false_pauses_015,
            "false_pause_rate_015": fp_rate_015,
            "missed_poor_015": missed_poor_015,
            "missed_poor_rate_015": missed_rate_015,
            "spend_on_poor_015": spend_on_poor_015,
            "good_ads_010": good_ads_010,
            "poor_ads_010": poor_ads_010,
            "false_pauses_010": false_pauses_010,
            "false_pause_rate_010": fp_rate_010,
            "missed_poor_010": missed_poor_010,
            "missed_poor_rate_010": missed_rate_010,
            "spend_on_poor_010": spend_on_poor_010,
            "mean_pause_day": mean_pause_day,
            "pause_day_counts": pause_day_counts,
            "total_spend": total_spend,
            "total_ql": total_ql,
            "cpql": cpql,
            "paused_count": len(pause_days),
        }

    with open("scratch/step_4d41_evaluation_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 90)
    print("STEP 4D.4.1 EVALUATION RESULTS SUMMARY")
    print("=" * 90)
    for c_key, res in results.items():
        print(f"\n--- {res['name']} ({c_key}) ---")
        print(f"Intercepted Count: {res['intercepted_count']}")
        print(f"Total Ads: {res['total_ads']} | Total Paused: {res['paused_count']} | Pause Days: {res['pause_day_counts']} (Mean: {res['mean_pause_day']:.2f})")
        print(f"Benchmark Hurdle 0.15 (Good: {res['good_ads_015']}, Poor: {res['poor_ads_015']}):")
        print(f"  False Pauses: {res['false_pauses_015']}/{res['good_ads_015']} ({res['false_pause_rate_015']*100:.2f}%)")
        print(f"  Missed Poor Ads: {res['missed_poor_015']}/{res['poor_ads_015']} ({res['missed_poor_rate_015']*100:.2f}%)")
        print(f"  Spend on Poor Ads: ₹{res['spend_on_poor_015']:,.2f}")
        print(f"Production Hurdle 0.10 (Good: {res['good_ads_010']}, Poor: {res['poor_ads_010']}):")
        print(f"  False Pauses: {res['false_pauses_010']}/{res['good_ads_010']} ({res['false_pause_rate_010']*100:.2f}%)")
        print(f"  Missed Poor Ads: {res['missed_poor_010']}/{res['poor_ads_010']} ({res['missed_poor_rate_010']*100:.2f}%)")
        print(f"  Spend on Poor Ads: ₹{res['spend_on_poor_010']:,.2f}")
        print(f"Global Portfolio:")
        print(f"  Total Spend: ₹{res['total_spend']:,.2f} | Total QL: {res['total_ql']} | CPQL: ₹{res['cpql']:.2f}")

if __name__ == "__main__":
    run_evaluation()
