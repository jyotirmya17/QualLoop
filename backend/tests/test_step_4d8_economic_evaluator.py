"""
Unit and boundary tests for Step 4D.8 Economic Viability Evaluator Prototype.
Verifies:
1. Breakeven CPQL and breakeven qualification rate calculations.
2. Handling of insufficient evidence (maturity fraction and mature contacts).
3. Correct economic discrimination:
   - Cheap ad with low qualification rate is KEPT RUNNING (profitable).
   - Expensive ad with high qualification rate is PAUSED (unprofitable).
4. Segment-specific heterogeneous lead valuation.
5. Strict isolation: Evaluator does not access simulator ground truth.
"""

import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path
import pytest

# Ensure repo root is on sys.path to import scratch module
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scratch.economic_evaluator import (
    EconomicAction,
    EconomicParameters,
    evaluate_ad_economic_viability,
)


@dataclass
class MockCampaignEstimate:
    """Mock estimate snapshot containing only observable fields."""
    advertisement_id: str
    n_leads: int
    n_call_attempts: int
    n_mature_leads: int
    n_mature_contacts: int
    contact_maturity_fraction: float
    k_contacts: int
    k_qualified: int
    reachability_mean: float
    qualification_mean: float


def test_evaluator_strict_isolation_no_ground_truth():
    """Verify evaluator signature and code do not accept or reference ground_truth."""
    sig = inspect.signature(evaluate_ad_economic_viability)
    param_names = list(sig.parameters.keys())
    assert "ground_truth" not in param_names
    assert "true_intent" not in param_names
    assert "true_reachability" not in param_names

    # Check source code does not access ground_truth
    source = inspect.getsource(evaluate_ad_economic_viability)
    assert "ground_truth" not in source
    assert "true_intent" not in source


def test_insufficient_evidence_gating():
    """Verify evaluator defers when maturity fraction or sample size is insufficient."""
    params = EconomicParameters(lead_value=600.0, min_mature_contacts=20, min_maturity_fraction=0.60)

    # 1. Low maturity fraction
    snap_low_mat = MockCampaignEstimate(
        advertisement_id="ad-1", n_leads=50, n_call_attempts=50, n_mature_leads=20,
        n_mature_contacts=15, contact_maturity_fraction=0.40, k_contacts=12, k_qualified=1,
        reachability_mean=0.60, qualification_mean=0.08
    )
    res_mat = evaluate_ad_economic_viability(snap_low_mat, cumulative_spend=1000.0, current_day=7.0, params=params)
    assert res_mat.action == EconomicAction.INSUFFICIENT_EVIDENCE
    assert "maturity fraction" in res_mat.reason

    # 2. Low mature contacts
    snap_low_cont = MockCampaignEstimate(
        advertisement_id="ad-2", n_leads=50, n_call_attempts=50, n_mature_leads=35,
        n_mature_contacts=10, contact_maturity_fraction=0.70, k_contacts=10, k_qualified=1,
        reachability_mean=0.60, qualification_mean=0.08
    )
    res_cont = evaluate_ad_economic_viability(snap_low_cont, cumulative_spend=1000.0, current_day=7.0, params=params)
    assert res_cont.action == EconomicAction.INSUFFICIENT_EVIDENCE
    assert "mature contacts" in res_cont.reason


def test_cheap_low_intent_ad_kept_running():
    """
    Counterexample 1 Proof:
    Cheap ad (CPL = Rs 15, reach = 60%, qual = 8%).
    Under static 10% hurdle, this ad is falsely paused.
    Under economic evaluator with lead_value = Rs 600, CPQL = Rs 312.50 < Rs 600,
    so the ad is profitable and must be KEPT RUNNING.
    """
    snap_cheap = MockCampaignEstimate(
        advertisement_id="ad-cheap", n_leads=200, n_call_attempts=200, n_mature_leads=150,
        n_mature_contacts=90, contact_maturity_fraction=0.75, k_contacts=90, k_qualified=7,
        reachability_mean=0.60, qualification_mean=0.08
    )
    params = EconomicParameters(lead_value=600.0, min_mature_contacts=20, min_maturity_fraction=0.60)

    res = evaluate_ad_economic_viability(snap_cheap, cumulative_spend=3000.0, current_day=14.0, params=params)

    assert res.action == EconomicAction.CONTINUE
    assert res.expected_incremental_profit > 0
    assert res.expected_cpql < params.lead_value


def test_expensive_high_intent_ad_paused():
    """
    Counterexample 2 Proof:
    Expensive ad (CPL = Rs 100, reach = 60%, qual = 18%).
    Under static 10% or 15% hurdle, this ad is missed and continues running.
    Under economic evaluator with lead_value = Rs 600, CPQL = Rs 925 > Rs 600,
    so the ad destroys capital and must be PAUSED.
    """
    snap_exp = MockCampaignEstimate(
        advertisement_id="ad-exp", n_leads=50, n_call_attempts=50, n_mature_leads=40,
        n_mature_contacts=30, contact_maturity_fraction=0.80, k_contacts=24, k_qualified=5,
        reachability_mean=0.60, qualification_mean=0.17
    )
    params = EconomicParameters(lead_value=600.0, min_mature_contacts=20, min_maturity_fraction=0.60)

    res = evaluate_ad_economic_viability(snap_exp, cumulative_spend=5000.0, current_day=14.0, params=params)

    assert res.action == EconomicAction.PAUSE
    assert res.expected_incremental_profit < 0
    assert res.expected_cpql > params.lead_value


def test_segment_heterogeneous_valuation():
    """Verify that segmented valuation function dynamically alters recommendation."""
    snap = MockCampaignEstimate(
        advertisement_id="ad-tier", n_leads=100, n_call_attempts=100, n_mature_leads=80,
        n_mature_contacts=50, contact_maturity_fraction=0.80, k_contacts=40, k_qualified=5,
        reachability_mean=0.50, qualification_mean=0.10
    )

    def segment_value_fn(tier: str) -> float:
        return 1500.0 if tier == "enterprise" else 400.0

    params = EconomicParameters(
        lead_value=600.0,
        min_mature_contacts=20,
        min_maturity_fraction=0.60,
        segment_value_fn=segment_value_fn,
    )

    # 1. Under Enterprise tier (lead_value = Rs 1,500), CPQL Rs 800 is profitable -> CONTINUE
    res_ent = evaluate_ad_economic_viability(snap, cumulative_spend=4000.0, current_day=14.0, params=params, campaign_tier="enterprise")
    assert res_ent.action == EconomicAction.CONTINUE
    assert res_ent.metrics["lead_value"] == 1500.0

    # 2. Under SMB tier (lead_value = Rs 400), CPQL Rs 800 is unprofitable -> PAUSE
    res_smb = evaluate_ad_economic_viability(snap, cumulative_spend=4000.0, current_day=14.0, params=params, campaign_tier="smb")
    assert res_smb.action == EconomicAction.PAUSE
    assert res_smb.metrics["lead_value"] == 400.0
