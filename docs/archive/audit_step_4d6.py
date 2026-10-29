"""
Step 4D.6: Independent Recomputation & Audit of Economic Regret and Metrics

Recomputes from raw simulation domain objects from scratch:
1. Ground truth classification (q_true vs 0.10 and 0.15)
2. Policy execution trajectories (PROD_P10, PROD_P15, CONFIG_A_P15)
3. Spend and qualified lead accounting (Metric 1 and Metric 2)
4. Saved spend on good ads, lost leads on good ads
5. Excess spend on poor ads, excess leads on poor ads (relative to Day 14 oracle)
6. Linear regret coefficients A and B
7. Algebraic crossover points V_QL*
8. Sanity check: Total spend = spend_on_good + spend_on_poor
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
        ads.append(
            AdConfig(
                creative_id=f"cr-cont-{seed}-{i}",
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

def run_independent_audit():
    print("Re-generating simulations from scratch...")
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

    print(f"Generated {len(simulations)} paired simulation runs.")

    # Policies
    policies = {
        "PROD_P10": {
            "name": "Production Policy (ci=0.90, N=20, decision_thresh=0.10)",
            "est_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60, min_mature_leads=30),
            "dec_pol": DecisionPolicy(low_qualification_upper_bound=0.10, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60, min_mature_leads_for_reachability=30),
        },
        "PROD_P15": {
            "name": "Production Policy on 0.15 Hurdle (ci=0.90, N=20, decision_thresh=0.15)",
            "est_cfg": EstimatorConfig(ci_level=0.90, min_mature_contacts=20, min_maturity_fraction=0.60, min_mature_leads=30),
            "dec_pol": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=20, min_maturity_fraction=0.60, min_mature_leads_for_reachability=30),
        },
        "CONFIG_A_P15": {
            "name": "Step 4D Baseline Config A (ci=0.80, N=12, decision_thresh=0.15)",
            "est_cfg": EstimatorConfig(ci_level=0.80, min_mature_contacts=12, min_maturity_fraction=0.50, min_mature_leads=30),
            "dec_pol": DecisionPolicy(low_qualification_upper_bound=0.15, min_mature_contacts_for_qualification=12, min_maturity_fraction=0.50, min_mature_leads_for_reachability=30),
        },
    }

    audit_data = {}

    for pol_key, pol_info in policies.items():
        est_cfg = pol_info["est_cfg"]
        dec_pol = pol_info["dec_pol"]

        ad_records = []

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
                    config=est_cfg,
                    seed=seed,
                )

                decs = evaluate_campaign(
                    snapshots=snaps,
                    ad_spends={ad.id: accrued_spends[ad.id] for ad in active_ads},
                    policy=dec_pol,
                )

                for dec in decs:
                    if is_pause(dec.action) and paused_day[dec.advertisement_id] is None:
                        paused_day[dec.advertisement_id] = cp_day

            # Collect raw data for each ad
            for ad in sim.advertisements:
                gt = gt_by_ad[ad.id]
                q_true = float(np.mean(gt.true_intent_by_day))
                p_day = paused_day[ad.id]

                full_spend = float(ad.spend)
                all_quals = [l for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id]
                full_ql = len(all_quals)

                # Day 14 oracle benchmark
                t_d14 = epoch + np.timedelta64(14, "D").astype("timedelta64[s]").item()
                d14_spend = round(ad.spend * (14 / horizon), 2)
                d14_ql_m1 = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_d14 and l.id in qual_by_lead_id)

                if p_day is not None:
                    ad_spend = round(ad.spend * (p_day / horizon), 2)
                    t_p = epoch + np.timedelta64(p_day, "D").astype("timedelta64[s]").item()
                    m1_ql = sum(1 for l in leads_by_ad[ad.id] if l.created_at < t_p and l.id in qual_by_lead_id)
                    m2_ql = sum(1 for l in leads_by_ad[ad.id] if l.id in qual_by_lead_id and qual_by_lead_id[l.id].resolved_at <= t_p)
                else:
                    ad_spend = full_spend
                    m1_ql = full_ql
                    m2_ql = full_ql

                m1_lost_ql = full_ql - m1_ql
                m2_lost_ql = full_ql - m2_ql

                ad_records.append({
                    "family": family,
                    "scenario_name": sc_name,
                    "seed": seed,
                    "ad_id": ad.id,
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
                })

        audit_data[pol_key] = ad_records

    # Recompute Regret and Metrics for each policy and hurdle independently
    results = {}

    for pol_key, ad_records in audit_data.items():
        results[pol_key] = {}

        for h in [0.10, 0.15]:
            h_str = f"hurdle_{int(round(h*100)):02d}"

            good_ads = [a for a in ad_records if a["q_true"] >= h]
            poor_ads = [a for a in ad_records if a["q_true"] < h]

            # Denominator integrity check:
            assert len(good_ads) + len(poor_ads) == len(ad_records) == 450, "Partition failure!"

            # False Pauses
            false_pauses = [a for a in good_ads if a["paused_day"] is not None]
            fp_count = len(false_pauses)
            fp_rate, fp_low, fp_high = wilson_score_ci(fp_count, len(good_ads))

            # Missed Poor
            missed_poor = [a for a in poor_ads if a["paused_day"] is None]
            mp_count = len(missed_poor)
            mp_rate, mp_low, mp_high = wilson_score_ci(mp_count, len(poor_ads))

            # Paused poor ads
            paused_poor = [a for a in poor_ads if a["paused_day"] is not None]

            # Spend accounting
            spend_on_good = sum(a["spend"] for a in good_ads)
            spend_on_poor = sum(a["spend"] for a in poor_ads)
            spend_paused_poor = sum(a["spend"] for a in paused_poor)
            spend_missed_poor = sum(a["spend"] for a in missed_poor)
            total_spend = sum(a["spend"] for a in ad_records)

            # Spend integrity check:
            assert abs(total_spend - (spend_on_good + spend_on_poor)) < 1e-4, "Spend summation mismatch!"
            assert abs(spend_on_poor - (spend_paused_poor + spend_missed_poor)) < 1e-4, "Poor spend summation mismatch!"

            # Qualified Leads
            total_m1_ql = sum(a["m1_ql"] for a in ad_records)
            total_m2_ql = sum(a["m2_ql"] for a in ad_records)
            good_m1_ql = sum(a["m1_ql"] for a in good_ads)
            poor_m1_ql = sum(a["m1_ql"] for a in poor_ads)

            # Lead integrity check:
            assert total_m1_ql == (good_m1_ql + poor_m1_ql), "QL summation mismatch!"

            # Regret Components
            # 1. Good ads: Saved Spend and Lost QL
            good_saved_spend = sum(a["full_spend"] - a["spend"] for a in false_pauses)
            good_lost_ql = sum(a["m1_lost_ql"] for a in false_pauses)

            # 2. Poor ads: Excess Spend and Excess QL relative to Day 14 oracle
            # For each poor ad:
            # excess_spend = spend - d14_spend
            # excess_ql = m1_ql - d14_ql_m1
            poor_excess_spend = sum(max(0.0, a["spend"] - a["d14_spend"]) for a in poor_ads)
            poor_excess_ql = sum(max(0, a["m1_ql"] - a["d14_ql_m1"]) for a in poor_ads)

            # Regret coefficients:
            # Regret(V) = A + B * V
            # A = Net spend waste = poor_excess_spend - good_saved_spend
            # B = Net lost leads = good_lost_ql - poor_excess_ql
            A = poor_excess_spend - good_saved_spend
            B = good_lost_ql - poor_excess_ql

            # Portfolio CPQL
            cpql_m1 = round(total_spend / total_m1_ql, 2)
            cpql_m2 = round(total_spend / total_m2_ql, 2)

            pause_days = [a["paused_day"] for a in ad_records if a["paused_day"] is not None]
            pause_counts = {str(d): pause_days.count(d) for d in CHECKPOINTS}
            mean_pday = float(np.mean(pause_days)) if pause_days else None

            results[pol_key][h_str] = {
                "hurdle": h,
                "n_good": len(good_ads),
                "n_poor": len(poor_ads),
                "fp_count": fp_count,
                "fp_rate": round(fp_rate, 4),
                "fp_ci95": [round(fp_low, 4), round(fp_high, 4)],
                "mp_count": mp_count,
                "mp_rate": round(mp_rate, 4),
                "mp_ci95": [round(mp_low, 4), round(mp_high, 4)],
                "spend_total": total_spend,
                "spend_good": spend_on_good,
                "spend_poor": spend_on_poor,
                "spend_paused_poor": spend_paused_poor,
                "spend_missed_poor": spend_missed_poor,
                "total_m1_ql": total_m1_ql,
                "total_m2_ql": total_m2_ql,
                "good_lost_ql": good_lost_ql,
                "good_saved_spend": good_saved_spend,
                "poor_excess_spend": poor_excess_spend,
                "poor_excess_ql": poor_excess_ql,
                "A_spend_waste": A,
                "B_lost_leads": B,
                "cpql_m1": cpql_m1,
                "cpql_m2": cpql_m2,
                "pause_counts": pause_counts,
                "mean_pause_day": round(mean_pday, 2) if mean_pday else None,
            }

    # Verify Crossovers algebraically:
    crossovers = {}
    for h_str in ["hurdle_10", "hurdle_15"]:
        crossovers[h_str] = {}
        # PROD_P10 vs PROD_P15
        p1 = results["PROD_P10"][h_str]
        p2 = results["PROD_P15"][h_str]
        p3 = results["CONFIG_A_P15"][h_str]

        # V* (P10 vs P15) = (A10 - A15) / (B15 - B10)
        dA_12 = p1["A_spend_waste"] - p2["A_spend_waste"]
        dB_12 = p2["B_lost_leads"] - p1["B_lost_leads"]
        v_star_12 = dA_12 / dB_12
        crossovers[h_str]["PROD_P10_vs_PROD_P15"] = {
            "dA": dA_12,
            "dB": dB_12,
            "V_star": round(v_star_12, 2),
        }

        # V* (P10 vs Config A)
        dA_13 = p1["A_spend_waste"] - p3["A_spend_waste"]
        dB_13 = p3["B_lost_leads"] - p1["B_lost_leads"]
        v_star_13 = dA_13 / dB_13
        crossovers[h_str]["PROD_P10_vs_CONFIG_A_P15"] = {
            "dA": dA_13,
            "dB": dB_13,
            "V_star": round(v_star_13, 2),
        }

        # V* (P15 vs Config A)
        dA_23 = p2["A_spend_waste"] - p3["A_spend_waste"]
        dB_23 = p3["B_lost_leads"] - p2["B_lost_leads"]
        v_star_23 = dA_23 / dB_23
        crossovers[h_str]["PROD_P15_vs_CONFIG_A_P15"] = {
            "dA": dA_23,
            "dB": dB_23,
            "V_star": round(v_star_23, 2),
        }

    output = {
        "results": results,
        "crossovers": crossovers,
    }

    out_json = "scratch/step_4d6_regret_integrity_audit_v1.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Audit completed. Written to {out_json}")

if __name__ == "__main__":
    run_independent_audit()
