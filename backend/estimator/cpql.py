"""
CPQL (Cost Per Qualified Lead) estimation via Monte Carlo.

CPQL is a ratio estimator that becomes unstable when EQL (expected qualified
leads) is near zero. This module handles the instability explicitly by:
1. Computing a Monte Carlo distribution over EQL
2. Reporting the fraction of samples with zero qualified leads
3. Marking CPQL as unstable when zero-EQL fraction is high
4. Never hiding NaN or infinity behind arbitrary constants

See docs/STATISTICAL_MODEL.md §5 for specification.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from estimator.beta_binomial import BetaBinomialEstimate, sample_posterior


@dataclass(frozen=True)
class CPQLEstimate:
    """
    Estimated cost per qualified lead with uncertainty.

    Attributes:
        eql_mean: Mean estimated qualified leads
        eql_ci_low: Lower bound of EQL credible interval
        eql_ci_high: Upper bound of EQL credible interval
        cpql_mean: Mean CPQL (None if unstable)
        cpql_ci_low: Lower bound of CPQL interval (None if unstable)
        cpql_ci_high: Upper bound of CPQL interval (None if unstable)
        zero_eql_fraction: Fraction of Monte Carlo samples with EQL < 0.5
        unstable: True when zero_eql_fraction > threshold
        n_samples: Monte Carlo sample count used
    """

    eql_mean: float
    eql_ci_low: float
    eql_ci_high: float
    cpql_mean: float | None
    cpql_ci_low: float | None
    cpql_ci_high: float | None
    zero_eql_fraction: float
    unstable: bool
    n_samples: int


def estimate_cpql(
    spend: float,
    n_leads: float,
    maturity_fraction: float,
    reachability_estimate: BetaBinomialEstimate,
    qualification_estimate: BetaBinomialEstimate,
    n_samples: int = 10_000,
    ci_level: float = 0.90,
    instability_threshold: float = 0.20,
    rng: np.random.Generator | None = None,
) -> CPQLEstimate:
    """
    Estimate CPQL using Monte Carlo propagation of posterior uncertainty.

    Args:
        spend: Total advertising spend for the ad
        n_leads: Total number of leads for the ad
        maturity_fraction: Fraction of leads that are mature (n_mature / n_leads)
        reachability_estimate: BetaBinomialEstimate for reachability rate
        qualification_estimate: BetaBinomialEstimate for qualification rate
        n_samples: Monte Carlo sample count
        ci_level: Credible interval level
        instability_threshold: CPQL is marked unstable if zero_eql_fraction exceeds this
        rng: Optional numpy random generator for reproducibility

    Returns:
        CPQLEstimate with full uncertainty characterization

    Notes:
        EQL = n_leads * maturity_fraction * reachability * qualification
        When n_leads = 0 or spend = 0, returns a degenerate result with flags set.
    """
    if rng is None:
        rng = np.random.default_rng()

    alpha_tail = (1.0 - ci_level) / 2.0

    # Handle degenerate inputs
    if n_leads <= 0 or spend < 0:
        return CPQLEstimate(
            eql_mean=0.0,
            eql_ci_low=0.0,
            eql_ci_high=0.0,
            cpql_mean=None,
            cpql_ci_low=None,
            cpql_ci_high=None,
            zero_eql_fraction=1.0,
            unstable=True,
            n_samples=n_samples,
        )

    # Draw posterior samples
    p_r_samples = sample_posterior(reachability_estimate, n_samples=n_samples, rng=rng)
    p_q_samples = sample_posterior(qualification_estimate, n_samples=n_samples, rng=rng)

    # EQL Monte Carlo
    eql_samples = n_leads * maturity_fraction * p_r_samples * p_q_samples

    eql_mean = float(np.mean(eql_samples))
    eql_ci_low = float(np.percentile(eql_samples, alpha_tail * 100))
    eql_ci_high = float(np.percentile(eql_samples, (1.0 - alpha_tail) * 100))

    # Fraction of samples with near-zero EQL
    zero_eql_fraction = float(np.mean(eql_samples < 0.5))
    unstable = zero_eql_fraction > instability_threshold

    # CPQL from non-zero EQL samples only
    valid_mask = eql_samples >= 0.5
    if not np.any(valid_mask) or spend == 0.0:
        return CPQLEstimate(
            eql_mean=eql_mean,
            eql_ci_low=eql_ci_low,
            eql_ci_high=eql_ci_high,
            cpql_mean=None,
            cpql_ci_low=None,
            cpql_ci_high=None,
            zero_eql_fraction=zero_eql_fraction,
            unstable=True,
            n_samples=n_samples,
        )

    cpql_samples = spend / eql_samples[valid_mask]
    cpql_mean = float(np.mean(cpql_samples))
    cpql_ci_low = float(np.percentile(cpql_samples, alpha_tail * 100))
    cpql_ci_high = float(np.percentile(cpql_samples, (1.0 - alpha_tail) * 100))

    return CPQLEstimate(
        eql_mean=eql_mean,
        eql_ci_low=eql_ci_low,
        eql_ci_high=eql_ci_high,
        cpql_mean=cpql_mean,
        cpql_ci_low=cpql_ci_low,
        cpql_ci_high=cpql_ci_high,
        zero_eql_fraction=zero_eql_fraction,
        unstable=unstable,
        n_samples=n_samples,
    )
