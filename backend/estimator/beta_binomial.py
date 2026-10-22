"""
Beta-Binomial conjugate model for binary rate estimation.

Implements the core statistical model described in docs/STATISTICAL_MODEL.md.

Model:
    likelihood: k | n, p ~ Binomial(n, p)
    prior:      p ~ Beta(alpha_prior, beta_prior)
    posterior:  p | k, n ~ Beta(alpha_prior + k, beta_prior + n - k)

All credible intervals are computed exactly from the posterior Beta distribution.
No approximations (normal, etc.) are used.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from scipy import stats


def derive_rng(seed: int | None = None, entity_id: str = "") -> np.random.Generator:
    """
    Derive a deterministic NumPy Generator from (run seed, entity id).

    Guarantees that every random draw in the estimation pipeline is fully
    reproducible and isolated per entity (e.g. ad id).
    """
    base_seed = seed if seed is not None else 0
    h = hashlib.sha256(f"{base_seed}:{entity_id}".encode("utf-8")).digest()
    int_seed = int.from_bytes(h[:8], byteorder="big") % (2**63 - 1)
    return np.random.default_rng(int_seed)


@dataclass(frozen=True)
class BetaBinomialEstimate:
    """
    Result of a Beta-Binomial posterior computation.

    Attributes:
        n: number of trials (denominator)
        k: number of successes (numerator)
        alpha_prior: prior Beta alpha parameter
        beta_prior: prior Beta beta parameter
        posterior_mean: E[p | data] = (alpha_prior + k) / (alpha_prior + beta_prior + n)
        posterior_alpha: alpha_prior + k
        posterior_beta: beta_prior + n - k
        ci_low: lower bound of credible interval
        ci_high: upper bound of credible interval
        ci_level: credible interval level (e.g. 0.90)
        has_data: True if n > 0
    """

    n: int
    k: int
    alpha_prior: float
    beta_prior: float
    posterior_mean: float
    posterior_alpha: float
    posterior_beta: float
    ci_low: float
    ci_high: float
    ci_level: float
    has_data: bool


def estimate_rate(
    n: int,
    k: int,
    alpha_prior: float = 1.0,
    beta_prior: float = 1.0,
    ci_level: float = 0.90,
) -> BetaBinomialEstimate:
    """
    Compute a Beta-Binomial posterior estimate for a binary rate.

    Args:
        n: Number of trials (must be >= 0)
        k: Number of successes (must be >= 0 and <= n)
        alpha_prior: Prior Beta alpha parameter (default: 1 — uniform)
        beta_prior: Prior Beta beta parameter (default: 1 — uniform)
        ci_level: Credible interval level (default: 0.90)

    Returns:
        BetaBinomialEstimate with posterior mean and credible interval

    Raises:
        ValueError: if inputs are invalid

    Notes:
        When n == 0, returns the prior distribution.
        When k > n, raises ValueError.
        The posterior mean is Bayesian-regularized — it never reaches exactly 0 or 1
        unless the prior also has mass there.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    if k < 0:
        raise ValueError(f"k must be >= 0, got {k}")
    if k > n:
        raise ValueError(f"k ({k}) cannot exceed n ({n})")
    if alpha_prior <= 0:
        raise ValueError(f"alpha_prior must be > 0, got {alpha_prior}")
    if beta_prior <= 0:
        raise ValueError(f"beta_prior must be > 0, got {beta_prior}")
    if not (0.0 < ci_level < 1.0):
        raise ValueError(f"ci_level must be in (0, 1), got {ci_level}")

    posterior_alpha = alpha_prior + k
    posterior_beta = beta_prior + (n - k)
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)

    # Compute exact credible interval from Beta quantiles
    alpha_tail = (1.0 - ci_level) / 2.0
    dist = stats.beta(posterior_alpha, posterior_beta)
    ci_low = float(dist.ppf(alpha_tail))
    ci_high = float(dist.ppf(1.0 - alpha_tail))

    return BetaBinomialEstimate(
        n=n,
        k=k,
        alpha_prior=alpha_prior,
        beta_prior=beta_prior,
        posterior_mean=float(posterior_mean),
        posterior_alpha=float(posterior_alpha),
        posterior_beta=float(posterior_beta),
        ci_low=ci_low,
        ci_high=ci_high,
        ci_level=ci_level,
        has_data=(n > 0),
    )


def sample_posterior(
    estimate: BetaBinomialEstimate,
    n_samples: int = 10_000,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
    entity_id: str = "",
) -> np.ndarray:
    """
    Draw samples from the posterior Beta distribution.

    Used for Monte Carlo uncertainty propagation (e.g., CPQL estimation).

    Args:
        estimate: A BetaBinomialEstimate from estimate_rate()
        n_samples: Number of samples to draw
        rng: Optional numpy random generator
        seed: Optional seed to derive deterministic RNG if rng is None
        entity_id: Entity identifier (e.g. ad_id) for RNG derivation

    Returns:
        numpy array of shape (n_samples,) with values in [0, 1]
    """
    if rng is None:
        rng = derive_rng(seed, entity_id)

    return rng.beta(estimate.posterior_alpha, estimate.posterior_beta, size=n_samples)
