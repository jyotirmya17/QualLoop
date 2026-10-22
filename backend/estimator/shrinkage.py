"""
Empirical-Bayes hierarchical shrinkage via Method of Moments.

Fits Beta prior hyperparameters across all ads in a campaign or portfolio
to pool statistical strength, with minimum prior concentration constraints
and automatic fallback to fixed uninformative priors when too few ads exist.

See docs/STATISTICAL_MODEL.md §4 and docs/SPEC.md §3 for specification.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class EmpiricalBetaPrior:
    """Hyperparameters for a fitted Beta prior."""

    alpha: float
    beta: float
    mean: float
    sample_size: float  # kappa = alpha + beta (prior strength)
    is_empirical: bool
    n_source_ads: int


def fit_beta_prior_moments(
    observations: list[tuple[int, int]],  # (successes, trials)
    fallback_alpha: float,
    fallback_beta: float,
    min_ads: int = 3,
    min_trials_per_ad: int = 5,
    min_prior_strength: float = 4.0,
    max_prior_strength: float = 50.0,
) -> EmpiricalBetaPrior:
    """
    Fit Beta hyperparameters (alpha, beta) by Method of Moments across ads.

    Method of Moments:
        Given observed rates p_i = k_i / n_i across M qualifying ads (n_i >= min_trials):
        portfolio mean:  p_bar = sum(k_i) / sum(n_i)
        sample variance: s2    = var(p_i, ddof=1)
        concentration:   kappa = (p_bar * (1 - p_bar) / s2) - 1

    Enforces:
    1. Fallback to fixed prior if M < min_ads or p_bar in {0, 1}
    2. Minimum prior strength (kappa >= min_prior_strength) for stability
    3. Maximum prior strength (kappa <= max_prior_strength) to avoid over-rigidity

    Args:
        observations: List of (k_successes, n_trials) for each ad in campaign.
        fallback_alpha: Fallback alpha when too few ads or invalid variance.
        fallback_beta: Fallback beta when too few ads or invalid variance.
        min_ads: Minimum number of ads with sufficient trials required to fit.
        min_trials_per_ad: Minimum trials for an ad to be included in moment fitting (default 5).
        min_prior_strength: Minimum concentration kappa = alpha + beta (default 4.0).
        max_prior_strength: Maximum concentration kappa = alpha + beta (default 50.0).

    Returns:
        EmpiricalBetaPrior with alpha, beta, mean, kappa, and is_empirical flag.
    """
    fallback_strength = fallback_alpha + fallback_beta
    fallback_mean = fallback_alpha / fallback_strength

    # Filter ads with at least min_trials_per_ad
    valid_obs = [
        (float(k), float(n))
        for k, n in observations
        if n >= min_trials_per_ad and 0 <= k <= n
    ]

    if len(valid_obs) < min_ads:
        return EmpiricalBetaPrior(
            alpha=fallback_alpha,
            beta=fallback_beta,
            mean=fallback_mean,
            sample_size=fallback_strength,
            is_empirical=False,
            n_source_ads=len(valid_obs),
        )

    valid_rates = [k / n for k, n in valid_obs]
    total_k = sum(k for k, n in valid_obs)
    total_n = sum(n for k, n in valid_obs)

    if total_n <= 0:
        return EmpiricalBetaPrior(
            alpha=fallback_alpha,
            beta=fallback_beta,
            mean=fallback_mean,
            sample_size=fallback_strength,
            is_empirical=False,
            n_source_ads=len(valid_obs),
        )

    p_bar = total_k / total_n

    # If all rates are 0 or all are 1, moment estimation collapses
    if p_bar <= 0.0 or p_bar >= 1.0:
        return EmpiricalBetaPrior(
            alpha=fallback_alpha,
            beta=fallback_beta,
            mean=fallback_mean,
            sample_size=fallback_strength,
            is_empirical=False,
            n_source_ads=len(valid_obs),
        )

    s2 = float(np.var(valid_rates, ddof=1)) if len(valid_rates) > 1 else 0.0

    # If variance is near zero, clamp to max_prior_strength
    if s2 < 1e-6:
        kappa = max_prior_strength
    else:
        var_limit = p_bar * (1.0 - p_bar)
        if s2 >= var_limit:
            # Over-dispersed beyond theoretical maximum, clamp to min_prior_strength
            kappa = min_prior_strength
        else:
            kappa = (var_limit / s2) - 1.0

    # Enforce minimum and maximum prior strength
    kappa = max(min_prior_strength, min(max_prior_strength, kappa))

    alpha = p_bar * kappa
    beta = (1.0 - p_bar) * kappa

    # Safety clamps to ensure strictly positive parameters
    alpha = max(0.1, alpha)
    beta = max(0.1, beta)

    return EmpiricalBetaPrior(
        alpha=alpha,
        beta=beta,
        mean=alpha / (alpha + beta),
        sample_size=alpha + beta,
        is_empirical=True,
        n_source_ads=len(valid_obs),
    )
