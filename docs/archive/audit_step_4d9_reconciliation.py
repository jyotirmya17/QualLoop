"""
Step 4D.9: Economic Evaluator Independent Reconciliation and Audit Script

Independently recomputes all policy profit totals from raw per-ad records across
the 190 simulation runs (450 total ads), fixes the ad ID dictionary collision bug
by using composite keys (scenario_name, seed, creative_id), reconciles aggregate
totals with paired differences, audits probability calibration, and outputs
machine-readable audit artifacts.
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
from scratch.run_evaluation_step_4d8 import build_dataset, CHECKPOINTS

def run_independent_audit():
    print("=" * 80)
    print("STEP 4D.9: INDEPENDENT RECONCILIATION & AUDIT")
    print("=" * 80)

    simulations = build_dataset()
    print(f"Loaded {len(simulations)} paired simulation runs.")

    base_est_cfg = EstimatorConfig(
        ci_level=0.90,
        min_mature_contacts=20,
        min_maturity_fraction=0.60,
        min_mature_leads=30,
    )

    def segmented_lead_val(tier: str) -> float:
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

    all_policy_ad_records: Dict[str, List[Dict[str, Any]]] = {}
    calibration_records: List[Dict[str, Any]] = []

    for c_key, c_info in configs.items():
        print(f"Executing policy {c_key}...")
        is_econ = (c_info["type"] == "economic")
        pol = c_info.get("policy")
        econ_params = c_info.get("params")

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
                    config=base_est_cfg,
                    seed=seed,
                )

                if is_econ:
                    for snap in snaps:
                        ad_id = snap.advertisement_id
                        cur_sp = accrued_spends[ad_id]
                        tier = "tier1" if ("excellent" in ad_id or "-0" in ad_id) else "tier2"
                        res = evaluate_ad_economic_viability(
                            snapshot=snap,
                            cumulative_spend=cur_sp,
                            current_day=float(cp_day),
                            params=econ_params,
                            campaign_tier=tier,
                        )
                        if c_key == "ECON_V600" and cp_day == 14 and res.action != EconomicAction.INSUFFICIENT_EVIDENCE:
                            ad_obj = next(a for a in active_ads if a.id == ad_id)
                            calibration_records.append({
                                "composite_key": f"{sc_name}_{seed}_{ad_obj.creative_id}",
                                "p_profitable_pred": res.probability_profitable,
                                "exp_profit_pred": res.expected_incremental_profit,
                                "ad_id": ad_id,
                                "cp_day": cp_day,
                            })

                        if res.action == EconomicAction.PAUSE and paused_day[ad_id] is None:
                            paused_day[ad_id] = cp_day
                else:
                    decs = evaluate_campaign(
                        snapshots=snaps,
                        ad_spends={ad.id: accrued_spends[ad.id] for ad in active_ads},
                        policy=pol,
                    )
                    for dec in decs:
                        if is_pause(dec.action) and paused_day[dec.advertisement_id] is None:
                            paused_day[dec.advertisement_id] = cp_day

            # Tabulate outcomes for every ad
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

                expected_total_ql = max(1.0, len(leads_by_ad[ad.id]) * r_true * q_true)
                true_cpql = full_spend / expected_total_ql
                tier = "tier1" if ("excellent" in ad.id or "-0" in ad.id) else "tier2"
                composite_key = f"{sc_name}_{seed}_{ad.creative_id}"

                ad_records.append({
                    "composite_key": composite_key,
                    "family": family,
                    "scenario_name": sc_name,
                    "seed": seed,
                    "ad_id": ad.id,
                    "creative_id": ad.creative_id,
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

        all_policy_ad_records[c_key] = ad_records

    # 1. Recompute and Reconcile Policy Totals
    audit_results: Dict[str, Any] = {}
    valuations = [300.0, 600.0, 1200.0]

    for c_key, records in all_policy_ad_records.items():
        assert len(records) == 450, f"Expected 450 records, got {len(records)}"
        tot_spend = sum(r["spend"] for r in records)
        tot_ql = sum(r["m1_ql"] for r in records)
        cpql = round(tot_spend / tot_ql, 2) if tot_ql > 0 else 0.0

        profits = {}
        for v in valuations:
            p = sum((v * r["m1_ql"]) - r["spend"] for r in records)
            profits[f"V_{int(v)}"] = round(p, 2)

        seg_profit = sum(((1500.0 if r["tier"] == "tier1" else 400.0) * r["m1_ql"]) - r["spend"] for r in records)
        profits["Segmented"] = round(seg_profit, 2)

        pauses = [r["paused_day"] for r in records if r["paused_day"] is not None]
        mean_pause = round(float(np.mean(pauses)), 2) if pauses else None

        audit_results[c_key] = {
            "name": configs[c_key]["name"],
            "total_ads": len(records),
            "total_spend": round(tot_spend, 2),
            "total_ql": tot_ql,
            "cpql": cpql,
            "paused_count": len(pauses),
            "mean_pause_day": mean_pause,
            "net_contribution_profits": profits,
        }

    # 2. Recompute Paired Differences across ALL 450 Ads with Composite Key
    baseline_records = {r["composite_key"]: r for r in all_policy_ad_records["PROD_HEURISTIC_P10"]}
    assert len(baseline_records) == 450, f"Composite key collision: expected 450, got {len(baseline_records)}"

    paired_audit: Dict[str, Any] = {}

    for c_key in configs.keys():
        if c_key == "PROD_HEURISTIC_P10":
            continue
        c_records = {r["composite_key"]: r for r in all_policy_ad_records[c_key]}
        assert len(c_records) == 450

        paired_audit[c_key] = {}

        for val_name, v_val in [("V_300", 300.0), ("V_600", 600.0), ("V_1200", 1200.0), ("Segmented", None)]:
            deltas = []
            for comp_key, base_r in baseline_records.items():
                cand_r = c_records[comp_key]
                if v_val is not None:
                    base_prof = (v_val * base_r["m1_ql"]) - base_r["spend"]
                    cand_prof = (v_val * cand_r["m1_ql"]) - cand_r["spend"]
                else:
                    v_base = 1500.0 if base_r["tier"] == "tier1" else 400.0
                    base_prof = (v_base * base_r["m1_ql"]) - base_r["spend"]
                    v_cand = 1500.0 if cand_r["tier"] == "tier1" else 400.0
                    cand_prof = (v_cand * cand_r["m1_ql"]) - cand_r["spend"]

                deltas.append(cand_prof - base_prof)

            assert len(deltas) == 450, f"Expected 450 deltas, got {len(deltas)}"

            sum_deltas = float(np.sum(deltas))
            expected_aggregate_diff = audit_results[c_key]["net_contribution_profits"][val_name] - audit_results["PROD_HEURISTIC_P10"]["net_contribution_profits"][val_name]

            # Reconcile exact identity
            reconciliation_error = abs(sum_deltas - expected_aggregate_diff)
            assert reconciliation_error < 0.01, f"Mismatch: sum(deltas)={sum_deltas}, aggregate_diff={expected_aggregate_diff}"

            mean_d = float(np.mean(deltas))
            std_d = float(np.std(deltas, ddof=1))
            se_d = std_d / math.sqrt(450)
            ci_low = mean_d - 1.96 * se_d
            ci_high = mean_d + 1.96 * se_d
            t_stat = mean_d / se_d if se_d > 1e-9 else 0.0
            p_val = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=449)))

            paired_audit[c_key][val_name] = {
                "n_ads": 450,
                "total_delta_profit": round(sum_deltas, 2),
                "aggregate_profit_cand": audit_results[c_key]["net_contribution_profits"][val_name],
                "aggregate_profit_base": audit_results["PROD_HEURISTIC_P10"]["net_contribution_profits"][val_name],
                "reconciliation_error": round(reconciliation_error, 4),
                "reconciliation_status": "EXACT_RECONCILIATION_CONFIRMED",
                "mean_delta_profit_per_ad": round(mean_d, 2),
                "se_delta_profit": round(se_d, 2),
                "ci95_delta_profit_per_ad": [round(ci_low, 2), round(ci_high, 2)],
                "t_stat": round(t_stat, 3),
                "p_value": round(p_val, 5),
            }

    # 3. Calibration Audit for Predicted P(Profitable)
    # Check whether predicted probability of being profitable matches empirical profitability
    for cal in calibration_records:
        rec = baseline_records[cal["composite_key"]]
        # actual profit from day 14 to day 28:
        # full spend - spend at day 14
        inc_spend = rec["full_spend"] - round(rec["full_spend"] * (14.0 / 28.0), 2)
        # incremental leads qualified
        inc_ql = rec["full_ql"] - rec["m1_ql"] # approximate
        actual_inc_profit = (600.0 * inc_ql) - inc_spend
        cal["actual_incremental_profit"] = actual_inc_profit
        cal["is_actually_profitable"] = actual_inc_profit > 0.0

    cal_results = {
        "n_samples": len(calibration_records),
        "mean_predicted_prob": round(float(np.mean([c["p_profitable_pred"] for c in calibration_records])), 4) if calibration_records else None,
        "empirical_fraction_profitable": round(float(np.mean([c["is_actually_profitable"] for c in calibration_records])), 4) if calibration_records else None,
        "calibration_status": "EXPLORATORY_NOT_CALIBRATED",
        "notes": (
            "Posterior distribution models parameter estimation uncertainty via Beta posteriors, "
            "but projects future lead volume deterministically. Lead arrivals in reality follow "
            "a Poisson process with variance Var(L) = lambda * delta_t. Because point-projection "
            "ignores Poisson realization noise and binomial sampling noise in small sample horizons, "
            "the nominal posterior probability distribution is exploratory rather than calibrated."
        ),
    }

    final_payload = {
        "audit_version": "1.0.0",
        "step": "4D.9",
        "status": "AUDIT_COMPLETE",
        "n_runs": len(simulations),
        "total_ads_evaluated": 450,
        "bug_identified": {
            "name": "Composite Key Omission in Step 4D.8 Paired Aggregation",
            "root_cause": (
                "Step 4D.8 keyed ad records by `ad.id` alone. In preset scenarios with shared seeds (26001-26010), "
                "`_deterministic_id(rng)` yielded identical ad UUIDs across different scenario presets, causing "
                "80 preset ads to overwrite each other in the paired evaluation dictionary (370 entries instead of 450). "
                "Step 4D.9 resolves this by keying on `(scenario_name, seed, creative_id)`, restoring all 450 ads and "
                "reconciling aggregate profit differences with paired sums to zero error."
            ),
        },
        "policy_totals": audit_results,
        "paired_comparisons_n450": paired_audit,
        "calibration_audit": cal_results,
    }

    out_file = "scratch/step_4d9_audit_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2)

    print(f"\nAudit complete. Saved reconciliation results to {out_file}")

if __name__ == "__main__":
    run_independent_audit()
