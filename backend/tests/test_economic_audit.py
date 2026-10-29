"""
Step 4D.9: Economic Evaluator Integrity and Shadow-Mode Readiness Audit Tests

Validates:
1. Reconciliation between policy aggregate profits and paired per-ad sums.
2. Composite key uniqueness preventing ad ID collisions across preset runs.
3. Decision-time information isolation (zero future outcomes or ground truth).
4. Exploratory calibration labeling when predictive calibration is unverified.
"""

import inspect
import json
import math
from pathlib import Path
import sys
import numpy as np
import pytest

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.shadow.economic_evaluator import (
    EconomicAction,
    EconomicParameters,
    evaluate_ad_economic_viability,
)
from backend.shadow.dataset import build_dataset

def test_composite_key_uniqueness_across_presets():
    """Verify composite key (scenario_name, seed, creative_id) resolves collisions in presets."""
    sims = build_dataset()
    raw_ad_ids = [ad.id for item in sims for ad in item["sim"].advertisements]
    assert len(raw_ad_ids) == 450
    # Demonstrates that raw ad UUIDs have collisions across presets with identical seeds
    assert len(set(raw_ad_ids)) == 370, "Expected exactly 370 unique raw UUIDs due to seed sharing"

    # Composite key must be 100% unique
    composite_keys = [
        f"{item['scenario_name']}_{item['seed']}_{ad.creative_id}"
        for item in sims
        for ad in item["sim"].advertisements
    ]
    assert len(composite_keys) == 450
    assert len(set(composite_keys)) == 450, "Composite key must be completely unique across all 450 ads"

def test_aggregate_profit_reconciles_to_paired_sum():
    """Verify that aggregate profit differences equal paired per-ad difference sums to 0.00."""
    audit_file = repo_root / "docs" / "archive" / "audit_results.json"
    assert audit_file.exists(), "Audit results JSON must exist"

    with open(audit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    paired = data["paired_comparisons_n450"]
    for pol_key, scenarios in paired.items():
        for val_scenario, stats in scenarios.items():
            agg_cand = stats["aggregate_profit_cand"]
            agg_base = stats["aggregate_profit_base"]
            expected_delta = agg_cand - agg_base
            actual_sum = stats["total_delta_profit"]

            assert abs(actual_sum - expected_delta) < 1e-4, (
                f"Mismatch in {pol_key} ({val_scenario}): sum(deltas)={actual_sum} vs "
                f"agg_diff={expected_delta}"
            )
            assert stats["reconciliation_status"] == "EXACT_RECONCILIATION_CONFIRMED"

def test_decision_time_isolation_strictly_enforced():
    """Inspect evaluate_ad_economic_viability to guarantee no ground truth or future leaks."""
    sig = inspect.signature(evaluate_ad_economic_viability)
    for forbidden in ["ground_truth", "future", "true_intent", "true_reachability", "outcome"]:
        assert forbidden not in sig.parameters

    source = inspect.getsource(evaluate_ad_economic_viability)
    for forbidden_attr in ["true_intent", "true_reachability", "true_cpql", "full_spend", "full_ql"]:
        assert forbidden_attr not in source

def test_calibration_exploratory_flag_enforced():
    """Verify that uncalibrated posterior profit probabilities are labeled exploratory."""
    audit_file = repo_root / "docs" / "archive" / "audit_results.json"
    with open(audit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    cal = data["calibration_audit"]
    assert cal["calibration_status"] == "EXPLORATORY_NOT_CALIBRATED"
    assert "exploratory" in cal["notes"].lower()
