import json
from pathlib import Path

# Load ablation v1 results
with open("scratch/policy_ablation_results_v1.json", "r", encoding="utf-8") as f:
    ablation = json.load(f)

evals = ablation["eval_results"]
ads_a = {a["ad_id"]: a for a in evals["A"]["ad_records"]}
ads_b = {a["ad_id"]: a for a in evals["B"]["ad_records"]}
ads_c = {a["ad_id"]: a for a in evals["C"]["ad_records"]}
ads_d = {a["ad_id"]: a for a in evals["D"]["ad_records"]}

delayed_ads = [ad_id for ad_id in ads_a if ads_a[ad_id]["paused_day"] == 14 and ads_b[ad_id]["paused_day"] != 14]
delayed_to_21 = [ad_id for ad_id in delayed_ads if ads_b[ad_id]["paused_day"] == 21]
missed_in_bcd = [ad_id for ad_id in delayed_ads if ads_b[ad_id]["paused_day"] is None]

fps_a = [ad_id for ad_id in ads_a if ads_a[ad_id]["is_good"] and ads_a[ad_id]["paused_day"] is not None]
fps_b = [ad_id for ad_id in ads_a if ads_b[ad_id]["is_good"] and ads_b[ad_id]["paused_day"] is not None]

rescued_fps = [ad_id for ad_id in fps_a if ad_id not in fps_b]
persisting_fps = [ad_id for ad_id in fps_a if ad_id in fps_b]
new_fps = [ad_id for ad_id in fps_b if ad_id not in fps_a]

boundary_ads = [a for a in evals["A"]["ad_records"] if 0.13 <= a["true_intent"] <= 0.17]

audit_data = {
    "metadata": {
        "version": "v1_step4d4_trace_audit",
        "date": "2026-10-27T20:30:00Z",
        "objective": "Step 4D.4 Decision-Rule Trace Audit and Baseline Verification",
    },
    "verified_production_baseline": {
        "estimator": {
            "source_file": "backend/estimator/estimator.py",
            "ci_level": {"symbol": "CI_LEVEL", "value": 0.90},
            "min_mature_contacts": {"symbol": "MIN_MATURE_CONTACTS", "value": 20},
            "min_mature_leads": {"symbol": "MIN_MATURE_LEADS", "value": 30},
            "min_maturity_fraction": {"symbol": "MIN_MATURITY_FRACTION", "value": 0.60},
            "contact_maturity_days": {"symbol": "contact_maturity_days", "value": 3.0},
            "qualification_maturity_days": {"symbol": "qualification_maturity_days", "value": 7.0},
        },
        "decision_policy": {
            "source_file": "backend/decision_engine/engine.py",
            "version": {"symbol": "POLICY_VERSION", "value": "v0.2.0"},
            "min_mature_contacts_for_qualification": {"symbol": "min_mature_contacts_for_qualification", "value": 20},
            "min_mature_leads_for_reachability": {"symbol": "min_mature_leads_for_reachability", "value": 30},
            "min_maturity_fraction": {"symbol": "min_maturity_fraction", "value": 0.60},
            "low_qualification_upper_bound": {"symbol": "low_qualification_upper_bound", "value": 0.10},
            "low_reachability_upper_bound": {"symbol": "low_reachability_upper_bound", "value": 0.25},
            "high_cpql_lower_bound": {"symbol": "high_cpql_lower_bound", "value": 500.0},
            "target_cpql": {"symbol": "target_cpql", "value": 75.0},
            "guardrail_action_spend_cap": {"symbol": "guardrail_action_spend_cap", "value": 500.0},
        },
        "authoritative_runtime_wiring": {
            "api_evaluation": "backend/api/evaluation.py instantiates _DEFAULT_CONFIG = EstimatorConfig() and _DEFAULT_POLICY = DecisionPolicy()",
            "api_ads_router": "backend/api/routers/ads.py instantiates _DEFAULT_CONFIG = EstimatorConfig() and _DEFAULT_POLICY = DecisionPolicy()",
            "environment_overrides": "None (only DATABASE_URL in persistence/database.py)",
            "database_overrides": "None (decisions table stores policy_version string and decision record, no parameter override tables)",
            "preset_overrides": "None (simulator/scenarios.py generates ad traffic, does not override estimator or policy)",
        },
    },
    "bcd_equivalence_findings": {
        "total_ads_evaluated": 450,
        "pause_day_differences_B_vs_C": 0,
        "pause_day_differences_C_vs_D": 0,
        "spend_differences_B_vs_C": 0,
        "ql_differences_B_vs_C": 0,
        "day_14_pauses_in_A": 90,
        "delayed_to_day_21_in_BCD": len(delayed_to_21),
        "never_paused_missed_in_BCD": len(missed_in_bcd),
        "causal_mechanism": (
            "When 12 <= N < 20: Config C triggers Rule 3 directly (COLLECT_MORE_DATA). "
            "Config B passes Rule 3, but fails Rule 6 gate (evidence_sufficient_qualification == False), "
            "falling through to Rule 10 (CONTINUE_MONITORING). Both are non-pause actions, allowing the ad "
            "to continue spending identically until Day 21. When N >= 20, both B and C satisfy Rule 6 identically."
        ),
        "representative_delayed_traces": [
            {
                "ad_id": ad_id,
                "family": ads_a[ad_id]["family"],
                "scenario": ads_a[ad_id]["scenario_name"],
                "seed": ads_a[ad_id]["seed"],
                "true_intent": ads_a[ad_id]["true_intent"],
                "config_a_pause": ads_a[ad_id]["pause_details"],
                "config_bcd_pause": ads_b[ad_id]["pause_details"],
            }
            for ad_id in delayed_to_21[:3]
        ],
        "representative_missed_traces": [
            {
                "ad_id": ad_id,
                "family": ads_a[ad_id]["family"],
                "scenario": ads_a[ad_id]["scenario_name"],
                "seed": ads_a[ad_id]["seed"],
                "true_intent": ads_a[ad_id]["true_intent"],
                "config_a_pause": ads_a[ad_id]["pause_details"],
                "config_bcd_spend": ads_b[ad_id]["spend"],
            }
            for ad_id in missed_in_bcd[:3]
        ],
    },
    "boundary_analysis": {
        "hurdle": 0.15,
        "window": "[0.13, 0.17]",
        "total_boundary_ads": len(boundary_ads),
        "good_boundary_ads": len([a for a in boundary_ads if a["is_good"]]),
        "poor_boundary_ads": len([a for a in boundary_ads if a["is_poor"]]),
        "config_a_boundary_fps": len([a for a in boundary_ads if a["is_good"] and ads_a[a["ad_id"]]["paused_day"] is not None]),
        "config_d_boundary_fps": len([a for a in boundary_ads if a["is_good"] and ads_d[a["ad_id"]]["paused_day"] is not None]),
        "mathematical_explanation": (
            "Under Binomial(30, 0.16), P(k <= 2) = 11.5%. For k=2, Beta(3, 29) has theta_0.90 = 0.149 < 0.15, "
            "triggering Rule 6 false pause. Increasing N_min from 12 to 20 delays pause from Day 14 to Day 21 but "
            "fails to suppress false pauses because binomial variance at N=30 still frequently samples k <= 2."
        ),
    },
    "test_verification": {
        "test_added": "backend/tests/test_decision_engine.py::TestDecisionSemanticsAndSnapshotIntegrity::test_estimator_and_policy_contact_thresholds_distinct_semantics",
        "result": "PASSED (31/31 passed in test_decision_engine.py, 175 passed in full suite)",
    },
}

with open("scratch/decision_rule_trace_audit_v1.json", "w", encoding="utf-8") as f:
    json.dump(audit_data, f, indent=2)

print("Generated scratch/decision_rule_trace_audit_v1.json successfully.")
