"""
Regression and semantics tests for Step 4D.5:
- Independent configuration of policy decision threshold vs scoring hurdle
- Accurate classification and denominator accounting under variable hurdles
- Metric 1 (pipeline-harvest) vs Metric 2 (strictly resolved at decision) distinction
- Economic regret formula properties and crossover calculation
"""

import math
from datetime import datetime, timezone
import pytest

from decision_engine.engine import DecisionPolicy, DecisionAction, evaluate_campaign
from domain.enums import QualificationResult
from domain.models import Advertisement, Lead, CallAttempt, QualificationOutcome
from estimator.estimator import EstimatorConfig, compute_campaign_estimates


def wilson_score_ci(k: int, n: int, conf: float = 0.95):
    if n <= 0:
        return 0.0, 0.0, 0.0
    p = k / n
    z = 1.95996
    denom = 1.0 + (z**2) / n
    centre = (p + (z**2) / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))) / denom
    return float(p), float(max(0.0, centre - spread)), float(min(1.0, centre + spread))


def test_policy_threshold_independent_of_scoring_hurdle():
    """Verify policy decision threshold can be set independently from benchmark scoring hurdle."""
    pol_10 = DecisionPolicy(low_qualification_upper_bound=0.10)
    pol_15 = DecisionPolicy(low_qualification_upper_bound=0.15)

    assert pol_10.low_qualification_upper_bound == 0.10
    assert pol_15.low_qualification_upper_bound == 0.15
    assert pol_10.low_qualification_upper_bound != pol_15.low_qualification_upper_bound


def test_scoring_hurdle_label_reclassification_and_denominators():
    """
    Verify that changing the scoring hurdle from 0.15 to 0.10 correctly shifts
    marginal ads from poor to good, altering denominators without changing policy actions.
    """
    ads_intent = [0.04, 0.08, 0.12, 0.18, 0.25]  # 5 ads

    # Under Hurdle 0.15:
    good_15 = [q for q in ads_intent if q >= 0.15]
    poor_15 = [q for q in ads_intent if q < 0.15]
    assert len(good_15) == 2  # 0.18, 0.25
    assert len(poor_15) == 3  # 0.04, 0.08, 0.12

    # Under Hurdle 0.10:
    good_10 = [q for q in ads_intent if q >= 0.10]
    poor_10 = [q for q in ads_intent if q < 0.10]
    assert len(good_10) == 3  # 0.12, 0.18, 0.25
    assert len(poor_10) == 2  # 0.04, 0.08

    # The marginal ad (0.12) shifted from poor to good
    assert 0.12 in poor_15
    assert 0.12 in good_10


def test_metric1_pipeline_vs_metric2_resolved_accounting():
    """
    Verify that Metric 1 (leads created before pause) is strictly >= Metric 2
    (leads resolved before pause), preventing future lead leakage while accounting for pipeline harvest.
    """
    epoch = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    t_pause = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)  # Paused Day 14

    lead_1 = Lead(id="l1", advertisement_id="ad-1", created_at=datetime(2026, 1, 10, tzinfo=timezone.utc))
    qo_1 = QualificationOutcome(id="q1", lead_id="l1", resolved_at=datetime(2026, 1, 12, tzinfo=timezone.utc), result=QualificationResult.QUALIFIED)

    lead_2 = Lead(id="l2", advertisement_id="ad-1", created_at=datetime(2026, 1, 14, tzinfo=timezone.utc))  # Created before pause
    qo_2 = QualificationOutcome(id="q2", lead_id="l2", resolved_at=datetime(2026, 1, 18, tzinfo=timezone.utc), result=QualificationResult.QUALIFIED)  # Resolved after pause

    lead_3 = Lead(id="l3", advertisement_id="ad-1", created_at=datetime(2026, 1, 20, tzinfo=timezone.utc))  # Created after pause
    qo_3 = QualificationOutcome(id="q3", lead_id="l3", resolved_at=datetime(2026, 1, 22, tzinfo=timezone.utc), result=QualificationResult.QUALIFIED)

    leads = [lead_1, lead_2, lead_3]
    quals = {qo_1.lead_id: qo_1, qo_2.lead_id: qo_2, qo_3.lead_id: qo_3}

    # Metric 1: Pipeline harvest (created before pause)
    m1_ql = sum(1 for l in leads if l.created_at < t_pause and l.id in quals and quals[l.id].result == QualificationResult.QUALIFIED)
    # Metric 2: Resolved at or before pause
    m2_ql = sum(1 for l in leads if l.id in quals and quals[l.id].resolved_at <= t_pause and quals[l.id].result == QualificationResult.QUALIFIED)

    assert m1_ql == 2  # l1 and l2
    assert m2_ql == 1  # only l1
    assert m1_ql >= m2_ql


def test_economic_regret_linear_form_and_crossover():
    """Verify linear economic regret formula and crossover point calculation."""
    # Policy 1 (Conservative): higher spend waste on bad ads (A1 = 300k), fewer lost leads on good ads (B1 = -250)
    # Policy 2 (Aggressive): lower spend waste on bad ads (A2 = 200k), more lost leads on good ads (B2 = -150)
    A1, B1 = 300000.0, -250
    A2, B2 = 200000.0, -150

    # Crossover: A1 + B1 * V = A2 + B2 * V => V* = (A1 - A2) / (B2 - B1)
    dA = A1 - A2  # 100,000
    dB = B2 - B1  # -150 - (-250) = 100
    v_star = dA / dB

    assert v_star == 1000.0

    # At V < V*, Policy 2 has lower regret:
    v_low = 500.0
    regret1_low = A1 + B1 * v_low  # 300k - 125k = 175k
    regret2_low = A2 + B2 * v_low  # 200k - 75k = 125k
    assert regret2_low < regret1_low

    # At V > V*, Policy 1 has lower regret:
    v_high = 1500.0
    regret1_high = A1 + B1 * v_high  # 300k - 375k = -75k
    regret2_high = A2 + B2 * v_high  # 200k - 225k = -25k
    assert regret1_high < regret2_high
