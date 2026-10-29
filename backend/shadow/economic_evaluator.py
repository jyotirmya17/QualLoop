"""
Isolated Economic Viability Evaluator Prototype

Evaluates campaign ad snapshots based on expected incremental contribution profit
rather than a static qualification-rate heuristic.

CRITICAL ARCHITECTURAL BOUNDARY:
This module receives only observable campaign estimates (spend, reachability posterior,
qualification posterior, lead counts) and parameterized business assumptions (lead value,
variable costs, target CPQL). It NEVER accesses simulator ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, Tuple, Callable
import math
import numpy as np
import scipy.stats as stats


class EconomicAction(str, Enum):
    CONTINUE = "CONTINUE"
    PAUSE = "PAUSE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EconomicParameters:
    """
    Business parameters specifying commercial unit economics.
    These are external business inputs, not learned statistical parameters.
    """
    lead_value: float = 600.0  # V_QL: contribution value per qualified lead (INR)
    cost_per_lead: float = 0.0  # c_lead: variable lead intake/review cost
    cost_per_call: float = 0.0  # c_call: telecalling dialer/rep cost per attempt
    decision_horizon_days: float = 7.0  # future window over which incremental impact is projected
    min_mature_contacts: int = 20  # minimum contacts before making economic pause decision
    min_maturity_fraction: float = 0.60  # minimum maturity fraction
    confidence_level: float = 0.90  # Bayesian confidence level (e.g. 0.90 => pause if P(profitable) <= 0.10)
    segment_value_fn: Optional[Callable[[str], float]] = None  # optional tier-specific valuation


@dataclass
class EconomicEvaluationResult:
    """Output of the economic evaluator for an ad snapshot."""
    action: EconomicAction
    expected_incremental_spend: float
    expected_incremental_ql: float
    expected_incremental_profit: float
    profit_ci_low: float
    profit_ci_high: float
    expected_cpql: float
    breakeven_cpql: float
    probability_profitable: float
    reason: str
    calibration_status: str = "EXPLORATORY_NOT_CALIBRATED"
    metrics: Dict[str, Any] = field(default_factory=dict)


def evaluate_ad_economic_viability(
    snapshot: Any,
    cumulative_spend: float,
    current_day: float,
    params: EconomicParameters,
    campaign_tier: Optional[str] = None,
) -> EconomicEvaluationResult:
    """
    Evaluates whether an ad is expected to generate positive contribution margin
    over the future decision horizon.

    Strictly isolated: does not access ground truth.
    """
    # 1. Resolve lead value (handling segment-level heterogeneity)
    v_ql = params.lead_value
    if params.segment_value_fn is not None and campaign_tier is not None:
        v_ql = params.segment_value_fn(campaign_tier)

    # 2. Evidence Sufficiency Gates (Sample Size & Maturity)
    mat_frac = getattr(snapshot, "maturity_fraction_contact", getattr(snapshot, "contact_maturity_fraction", 1.0))
    if mat_frac < params.min_maturity_fraction:
        return EconomicEvaluationResult(
            action=EconomicAction.INSUFFICIENT_EVIDENCE,
            expected_incremental_spend=0.0,
            expected_incremental_ql=0.0,
            expected_incremental_profit=0.0,
            profit_ci_low=0.0,
            profit_ci_high=0.0,
            expected_cpql=float("inf"),
            breakeven_cpql=v_ql,
            probability_profitable=0.5,
            reason=(
                f"Contact maturity fraction ({mat_frac:.1%}) below required "
                f"{params.min_maturity_fraction:.1%}. Continuing autonomous observation."
            ),
        )

    if snapshot.n_mature_contacts < params.min_mature_contacts:
        return EconomicEvaluationResult(
            action=EconomicAction.INSUFFICIENT_EVIDENCE,
            expected_incremental_spend=0.0,
            expected_incremental_ql=0.0,
            expected_incremental_profit=0.0,
            profit_ci_low=0.0,
            profit_ci_high=0.0,
            expected_cpql=float("inf"),
            breakeven_cpql=v_ql,
            probability_profitable=0.5,
            reason=(
                f"Observed {snapshot.n_mature_contacts} mature contacts (min {params.min_mature_contacts} required). "
                f"Statistical sample insufficient for economic pause decision."
            ),
        )

    # 3. Project Future Lead Arrival & Incremental Spend
    obs_days = max(current_day, 1.0)
    lead_rate_per_day = max(snapshot.n_leads / obs_days, 0.5)
    daily_spend = cumulative_spend / obs_days if obs_days > 0 else 0.0

    delta_t = params.decision_horizon_days
    proj_leads = lead_rate_per_day * delta_t
    proj_spend = daily_spend * delta_t

    # Observed Cost per Lead (CPL)
    cpl = (cumulative_spend / snapshot.n_leads) if snapshot.n_leads > 0 else 50.0

    # 4. Bayesian Posterior for Reachability and Qualification
    r_mean = snapshot.reachability_mean
    q_mean = snapshot.qualification_mean

    n_calls = getattr(snapshot, "n_call_attempts", None)
    attempts_per_lead = (n_calls / snapshot.n_leads) if (n_calls is not None and snapshot.n_leads > 0) else 1.5

    # Incremental Operational Costs
    c_ops = (params.cost_per_lead * proj_leads) + (params.cost_per_call * proj_leads * attempts_per_lead)

    # 5. Incremental Expected Qualified Leads & CPQL
    exp_ql = proj_leads * r_mean * q_mean
    exp_cpql = (proj_spend / exp_ql) if exp_ql > 0.001 else float("inf")

    # Breakeven CPQL:
    ops_per_ql = (c_ops / exp_ql) if exp_ql > 0.001 else 0.0
    breakeven_cpql = max(0.0, v_ql - ops_per_ql)

    # 6. Posterior Distribution of Incremental Contribution Profit
    rng = np.random.default_rng(seed=int(abs(hash(snapshot.advertisement_id)) % 2**32))
    n_samples = 4000

    k_contacts = getattr(snapshot, "n_contacts", getattr(snapshot, "k_contacts", 0))
    n_mat_leads = getattr(snapshot, "n_mature_leads", 0)
    k_qual = getattr(snapshot, "k_qualified", 0)
    n_mat_contacts = getattr(snapshot, "n_mature_contacts", 0)

    alpha_r = max(1.0 + k_contacts, 1.0)
    beta_r = max(1.0 + (n_mat_leads - k_contacts), 1.0)
    alpha_q = max(1.0 + k_qual, 1.0)
    beta_q = max(4.0 + (n_mat_contacts - k_qual), 1.0)

    r_samples = rng.beta(alpha_r, beta_r, size=n_samples)
    q_samples = rng.beta(alpha_q, beta_q, size=n_samples)

    ql_samples = proj_leads * r_samples * q_samples
    profit_samples = (v_ql * ql_samples) - proj_spend - c_ops

    exp_profit = float(np.mean(profit_samples))
    alpha_ci = 1.0 - params.confidence_level
    p_low = float(np.percentile(profit_samples, 100.0 * (alpha_ci / 2.0)))
    p_high = float(np.percentile(profit_samples, 100.0 * (1.0 - alpha_ci / 2.0)))
    prob_profitable = float(np.mean(profit_samples > 0.0))

    # 7. Economic Decision Criterion
    max_prob_profitable = 1.0 - params.confidence_level
    is_model_unprofitable = (exp_profit < 0.0) and (prob_profitable <= max_prob_profitable)

    if is_model_unprofitable:
        action = EconomicAction.PAUSE
        reason = (
            f"Exploratory model projection indicates negative incremental contribution profit over next "
            f"{delta_t:.0f} days: projected mean -Rs {abs(exp_profit):,.2f} [model-derived {int(params.confidence_level*100)}% interval: Rs {p_low:,.2f}, Rs {p_high:,.2f}]. "
            f"Projected CPQL (Rs {exp_cpql:.2f}) exceeds breakeven threshold (Rs {breakeven_cpql:.2f}) "
            f"given lead valuation of Rs {v_ql:.2f}. Exploratory model probability of profitability: {prob_profitable:.1%} (uncalibrated estimate)."
        )
    else:
        action = EconomicAction.CONTINUE
        reason = (
            f"Exploratory model projection indicates non-negative incremental contribution profit or plausible viability over next "
            f"{delta_t:.0f} days: projected mean Rs {exp_profit:,.2f} [model-derived {int(params.confidence_level*100)}% interval: Rs {p_low:,.2f}, Rs {p_high:,.2f}]. "
            f"Projected CPQL = Rs {exp_cpql:.2f} vs breakeven Rs {breakeven_cpql:.2f}. Exploratory model probability of profitability: {prob_profitable:.1%} (uncalibrated estimate)."
        )

    return EconomicEvaluationResult(
        action=action,
        expected_incremental_spend=round(proj_spend, 2),
        expected_incremental_ql=round(exp_ql, 2),
        expected_incremental_profit=round(exp_profit, 2),
        profit_ci_low=round(p_low, 2),
        profit_ci_high=round(p_high, 2),
        expected_cpql=round(exp_cpql, 2),
        breakeven_cpql=round(breakeven_cpql, 2),
        probability_profitable=round(prob_profitable, 4),
        reason=reason,
        metrics={
            "proj_leads": round(proj_leads, 2),
            "cpl": round(cpl, 2),
            "reach_mean": round(r_mean, 4),
            "qual_mean": round(q_mean, 4),
            "lead_value": v_ql,
            "c_ops": round(c_ops, 2),
        },
    )
