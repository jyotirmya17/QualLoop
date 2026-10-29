"""
CPQL (Cost Per Qualified Lead) estimation via Monte Carlo.

CPQL is a ratio estimator that becomes unstable when EQL (expected qualified
leads) is near zero. This module handles the instability explicitly by:
1. Computing a Monte Carlo distribution over EQL:
      eql^(i) = n_leads * maturity_fraction * p_r^(i) * p_q^(i)
   where p_r ~ Beta(alpha_r, beta_r) and p_q ~ Beta(alpha_q, beta_q).
2. Reporting the fraction of samples with zero/near-zero qualified leads (EQL < 0.5):
      zero_eql_fraction = P(EQL < 0.5)
3. Marking CPQL as unstable when zero_eql_fraction > instability_threshold (default 0.20).
4. Deriving CPQL point estimates and credible intervals from posterior draws:
      cpql^(i) = spend / eql^(i)  for eql^(i) >= 0.5
      cpql_mean = E[spend / EQL | EQL >= 0.5]
      cpql_ci = [percentile(alpha/2, cpql_samples), percentile(1 - alpha/2, cpql_samples)]

MATHEMATICAL NOTE ON JENSEN'S INEQUALITY:
Because f(x) = spend / x is strictly convex for x > 0 (f''(x) = 2*spend / x^3 > 0),
by Jensen's Inequality:
      E[spend / EQL] > spend / E[EQL]
whenever EQL has non-zero posterior uncertainty.
Consequently, cpql_mean will strictly exceed (spend / eql_mean).
This is not a defect or calculation error; cpql_mean is the true posterior expectation
of the cost-per-qualified-lead ratio, while spend / eql_mean is merely the plug-in
ratio of expectations (which underestimates expected cost under parameter uncertainty).
Both cpql_mean and [cpql_ci_low, cpql_ci_high] are derived from the identical posterior
quantity cpql_samples.

See docs/STATISTICAL_MODEL.md §5 for specification.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from estimator.beta_binomial import BetaBinomialEstimate, derive_rng, sample_posterior


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
    cpql_median: float | None = None
    is_truncated_mean: bool = True


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
    seed: int | None = None,
    ad_id: str = "",
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
        seed: Optional run seed to derive deterministic RNG if rng is None
        ad_id: Ad identifier for deterministic RNG isolation

    Returns:
        CPQLEstimate with full uncertainty characterization

    Notes:
        EQL = n_leads * maturity_fraction * reachability * qualification
        When n_leads = 0 or spend = 0, returns a degenerate result with flags set.
        Spend is scaled by maturity_fraction (mature_spend) so spend and leads
        are treated consistently across cohorts.
        Mean CPQL is a truncated conditional mean over samples with EQL >= 0.5.
    """
    if rng is None:
        rng = derive_rng(seed, ad_id)

    alpha_tail = (1.0 - ci_level) / 2.0

    # Handle degenerate inputs
    if n_leads <= 0 or spend < 0:
        return CPQLEstimate(
            eql_mean=0.0,
            eql_ci_low=0.0,
            eql_ci_high=0.0,
            cpql_mean=None,
            cpql_median=None,
            cpql_ci_low=None,
            cpql_ci_high=None,
            zero_eql_fraction=1.0,
            unstable=True,
            n_samples=n_samples,
            is_truncated_mean=True,
        )

    # Draw posterior samples
    p_r_samples = sample_posterior(reachability_estimate, n_samples=n_samples, rng=rng)
    p_q_samples = sample_posterior(qualification_estimate, n_samples=n_samples, rng=rng)

    # EQL Monte Carlo (mature expected qualified leads)
    eql_samples = n_leads * maturity_fraction * p_r_samples * p_q_samples

    eql_mean = float(np.mean(eql_samples))
    eql_ci_low = float(np.percentile(eql_samples, alpha_tail * 100))
    eql_ci_high = float(np.percentile(eql_samples, (1.0 - alpha_tail) * 100))

    # Fraction of samples with near-zero EQL
    zero_eql_fraction = float(np.mean(eql_samples < 0.5))
    unstable = zero_eql_fraction > instability_threshold

    # CPQL from non-zero EQL samples only (truncated conditional distribution)
    valid_mask = eql_samples >= 0.5
    effective_spend = spend * maturity_fraction
    if not np.any(valid_mask) or spend == 0.0 or effective_spend <= 0.0:
        return CPQLEstimate(
            eql_mean=eql_mean,
            eql_ci_low=eql_ci_low,
            eql_ci_high=eql_ci_high,
            cpql_mean=None,
            cpql_median=None,
            cpql_ci_low=None,
            cpql_ci_high=None,
            zero_eql_fraction=zero_eql_fraction,
            unstable=True,
            n_samples=n_samples,
            is_truncated_mean=True,
        )

    cpql_samples = effective_spend / eql_samples[valid_mask]
    cpql_mean = float(np.mean(cpql_samples))
    cpql_median = float(np.median(cpql_samples))
    cpql_ci_low = float(np.percentile(cpql_samples, alpha_tail * 100))
    cpql_ci_high = float(np.percentile(cpql_samples, (1.0 - alpha_tail) * 100))

    return CPQLEstimate(
        eql_mean=eql_mean,
        eql_ci_low=eql_ci_low,
        eql_ci_high=eql_ci_high,
        cpql_mean=cpql_mean,
        cpql_median=cpql_median,
        cpql_ci_low=cpql_ci_low,
        cpql_ci_high=cpql_ci_high,
        zero_eql_fraction=zero_eql_fraction,
        unstable=unstable,
        n_samples=n_samples,
        is_truncated_mean=True,
    )
