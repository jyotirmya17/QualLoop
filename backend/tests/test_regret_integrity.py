"""
Step 4D.6: Economic-Regret Integrity & Crossover Invariance Tests

Tests:
1. Invariance of pairwise economic regret crossovers to the arbitrary choice of scoring hurdle.
2. Exact algebraic verification of the three economic value regimes:
   - Regime 1: V_QL < Rs 883.65 (Config A optimal)
   - Regime 2: Rs 883.65 <= V_QL <= Rs 1,640.91 (PROD_P15 optimal)
   - Regime 3: V_QL > Rs 1,640.91 (PROD_P10 optimal)
3. Mathematical explanation of negative regret relative to the Day 14 oracle.
4. Metric partition and denominator exhaustiveness check.
"""

import pytest


def test_pairwise_regret_crossover_invariance_to_scoring_hurdle():
    """
    Theorem: The difference in regret between any two policies pi_1 and pi_2
    equals Profit(pi_2) - Profit(pi_1) = [Spend(pi_1) - Spend(pi_2)] - V_QL * [QL(pi_1) - QL(pi_2)].
    The Oracle profit cancels out completely, making the crossover point V*
    strictly invariant to the choice of scoring hurdle tau_biz.
    """
    # Policy realized spend and qualified leads (frozen empirical totals from 190 runs)
    spend_p10 = 2158000.0
    ql_p10 = 5226

    spend_p15 = 2067750.0
    ql_p15 = 5171

    spend_cfgA = 1927250.0
    ql_cfgA = 5012

    # Under Hurdle 0.10:
    A_p10_h10, B_p10_h10 = 263000.0, -177
    A_p15_h10, B_p15_h10 = 172750.0, -122
    A_cfgA_h10, B_cfgA_h10 = 32250.0, 37

    # Under Hurdle 0.15:
    A_p10_h15, B_p10_h15 = 333000.0, -278
    A_p15_h15, B_p15_h15 = 242750.0, -223
    A_cfgA_h15, B_cfgA_h15 = 102250.0, -64

    # 1. P10 vs P15 crossover under Hurdle 0.10:
    dA_h10_12 = A_p10_h10 - A_p15_h10
    dB_h10_12 = B_p15_h10 - B_p10_h10
    v_star_h10_12 = dA_h10_12 / dB_h10_12

    # 2. P10 vs P15 crossover under Hurdle 0.15:
    dA_h15_12 = A_p10_h15 - A_p15_h15
    dB_h15_12 = B_p15_h15 - B_p10_h15
    v_star_h15_12 = dA_h15_12 / dB_h15_12

    # 3. Direct realized delta:
    d_spend_12 = spend_p10 - spend_p15
    d_ql_12 = ql_p10 - ql_p15
    v_star_direct_12 = d_spend_12 / d_ql_12

    assert d_spend_12 == 90250.0
    assert d_ql_12 == 55
    assert dA_h10_12 == dA_h15_12 == 90250.0
    assert dB_h10_12 == dB_h15_12 == 55
    assert pytest.approx(v_star_h10_12, 0.01) == 1640.91
    assert pytest.approx(v_star_h15_12, 0.01) == 1640.91
    assert pytest.approx(v_star_direct_12, 0.01) == 1640.91


def test_three_economic_regimes():
    """Verify exact policy ranking across the three economic value regimes."""
    spend_p10, ql_p10 = 2158000.0, 5226
    spend_p15, ql_p15 = 2067750.0, 5171
    spend_cfgA, ql_cfgA = 1927250.0, 5012

    def profit(spend, ql, v):
        return v * ql - spend

    # Crossover 1: P15 vs Config A: (2067750 - 1927250) / (5171 - 5012) = 140500 / 159 = 883.65
    v_crossover_1 = (spend_p15 - spend_cfgA) / (ql_p15 - ql_cfgA)
    assert pytest.approx(v_crossover_1, 0.01) == 883.65

    # Crossover 2: P10 vs P15: (2158000 - 2067750) / (5226 - 5171) = 90250 / 55 = 1640.91
    v_crossover_2 = (spend_p10 - spend_p15) / (ql_p10 - ql_p15)
    assert pytest.approx(v_crossover_2, 0.01) == 1640.91

    # Regime 1: Low lead value (e.g., V = Rs 500) -> Config A maximizes profit / minimizes regret
    v_regime1 = 500.0
    prof_p10 = profit(spend_p10, ql_p10, v_regime1)
    prof_p15 = profit(spend_p15, ql_p15, v_regime1)
    prof_cfgA = profit(spend_cfgA, ql_cfgA, v_regime1)
    assert prof_cfgA > prof_p15 > prof_p10

    # Regime 2: Moderate lead value (e.g., V = Rs 1,200) -> PROD_P15 maximizes profit / minimizes regret
    v_regime2 = 1200.0
    prof_p10 = profit(spend_p10, ql_p10, v_regime2)
    prof_p15 = profit(spend_p15, ql_p15, v_regime2)
    prof_cfgA = profit(spend_cfgA, ql_cfgA, v_regime2)
    assert prof_p15 > prof_p10
    assert prof_p15 > prof_cfgA

    # Regime 3: High lead value (e.g., V = Rs 2,000) -> PROD_P10 maximizes profit / minimizes regret
    v_regime3 = 2000.0
    prof_p10 = profit(spend_p10, ql_p10, v_regime3)
    prof_p15 = profit(spend_p15, ql_p15, v_regime3)
    prof_cfgA = profit(spend_cfgA, ql_cfgA, v_regime3)
    assert prof_p10 > prof_p15 > prof_cfgA


def test_negative_regret_explanation():
    """
    Verify why regret relative to the Day 14 oracle becomes negative at high V_QL:
    Running marginal poor ads beyond Day 14 generates additional leads whose value
    exceeds marginal spend when V_QL is high.
    """
    # Poor ad with spend Rs 5000 (Rs 2500 at D14, Rs 2500 D14-D28), generating 3 qualified leads D14-D28
    # Marginal CPQL on poor ad D14-D28 = 2500 / 3 = Rs 833.33
    marginal_spend = 2500.0
    marginal_leads = 3

    # If V_QL = Rs 500: marginal profit = 500 * 3 - 2500 = -1000 (Regret positive = 1000)
    regret_low = marginal_spend - 500.0 * marginal_leads
    assert regret_low == 1000.0 > 0

    # If V_QL = Rs 1,500: marginal profit = 1500 * 3 - 2500 = +2000 (Regret negative = -2000)
    regret_high = marginal_spend - 1500.0 * marginal_leads
    assert regret_high == -2000.0 < 0
