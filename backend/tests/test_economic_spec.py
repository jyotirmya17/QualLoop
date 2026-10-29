"""
Unit tests for Step 4D.7: Decision Objective and Economic Model Specification
Verifies:
1. Mathematical derivation of breakeven qualification rate q* = CPL / (r * Target_CPQL).
2. Counterexample proofs demonstrating why static 10% and 15% hurdles fail economically.
3. True Economic Profit Oracle marginal CPQL condition.
4. Schema validation and internal consistency of step_4d7_economic_model_specification.json.
"""

import json
from pathlib import Path
import pytest


def test_breakeven_qualification_rate_derivation():
    """Verify q* = CPL / (r * Target_CPQL)."""
    # Baseline case: CPL = 30, r = 0.60, Target = 500
    cpl = 30.0
    r = 0.60
    target_cpql = 500.0

    q_star = cpl / (r * target_cpql)
    assert q_star == 0.10  # exactly 10%

    # Verify that at q*, realized CPQL equals Target CPQL
    realized_cpql = cpl / (r * q_star)
    assert realized_cpql == target_cpql


def test_counterexample_proofs_against_static_hurdles():
    """
    Formally verifies Counterexample 1 (cheap viable ad paused)
    and Counterexample 2 (expensive unviable ad missed) by static rate hurdles.
    """
    target_cpql = 500.0
    r = 0.60

    # Counterexample 1: Cheap CPL ad (CPL = 15, q = 0.08)
    # Breakeven rate is 5%. Ad has q = 8% -> Realized CPQL = 15 / (0.60 * 0.08) = 312.50
    cpl_cheap = 15.0
    q_cheap = 0.08
    cpql_cheap = cpl_cheap / (r * q_cheap)
    q_star_cheap = cpl_cheap / (r * target_cpql)

    assert q_star_cheap == 0.05
    assert cpql_cheap == 312.50
    assert cpql_cheap < target_cpql  # Profitable!
    assert q_cheap < 0.10  # But paused by 10% hurdle!
    assert q_cheap < 0.15  # And paused by 15% hurdle!

    # Counterexample 2: Expensive CPL ad (CPL = 90, q = 0.18)
    # Breakeven rate is 30%. Ad has q = 18% -> Realized CPQL = 90 / (0.60 * 0.18) = 833.33
    cpl_expensive = 90.0
    q_expensive = 0.18
    cpql_expensive = cpl_expensive / (r * q_expensive)
    q_star_expensive = cpl_expensive / (r * target_cpql)

    assert q_star_expensive == 0.30
    assert pytest.approx(cpql_expensive, 0.01) == 833.33
    assert cpql_expensive > target_cpql  # Capital destroying!
    assert q_expensive > 0.10  # But allowed to run by 10% hurdle!
    assert q_expensive > 0.15  # And allowed to run by 15% hurdle!


def test_true_economic_oracle_condition():
    """
    Verify the True Economic Oracle condition:
    Marginal profit(t > t*) < 0 <=> Marginal CPQL(t > t*) > V_QL.
    """
    v_ql = 1000.0

    # Case A: Poor ad generates 3 leads for Rs 2,500 spend between D14 and D28
    marginal_spend_a = 2500.0
    marginal_leads_a = 3
    marginal_cpql_a = marginal_spend_a / marginal_leads_a  # 833.33
    marginal_profit_a = v_ql * marginal_leads_a - marginal_spend_a  # 1000 * 3 - 2500 = +500

    # Since marginal_cpql < v_ql, marginal profit is positive. Oracle should NOT stop it!
    assert marginal_cpql_a < v_ql
    assert marginal_profit_a > 0

    # Case B: Worse ad generates 1 lead for Rs 2,500 spend between D14 and D28
    marginal_spend_b = 2500.0
    marginal_leads_b = 1
    marginal_cpql_b = marginal_spend_b / marginal_leads_b  # 2500.0
    marginal_profit_b = v_ql * marginal_leads_b - marginal_spend_b  # 1000 * 1 - 2500 = -1500

    # Since marginal_cpql > v_ql, marginal profit is negative. Oracle SHOULD stop it!
    assert marginal_cpql_b > v_ql
    assert marginal_profit_b < 0


def test_json_specification_schema_and_completeness():
    """Verify that the JSON specification file exists and contains all required sections."""
    spec_path = Path("docs/archive/economic_model_specification.json")
    assert spec_path.exists(), "JSON specification file missing!"

    with open(spec_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["specification_version"] == "1.0.0"
    assert data["step"] == "4D.7"
    assert "observable_quantities" in data
    assert "business_assumptions_unobservables" in data
    assert "expected_contribution_profit_model" in data
    assert "qualification_hurdle_economic_derivation" in data
    assert "oracle_classification" in data
    assert data["oracle_classification"]["classification"] == "HEURISTIC_COMPARATOR"
    assert data["oracle_classification"]["is_universal_optimum"] is False
    assert "data_collection_specification" in data
    assert "success_criteria_next_experiment" in data
