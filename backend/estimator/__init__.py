"""Estimator package."""

from estimator.beta_binomial import BetaBinomialEstimate, estimate_rate, sample_posterior
from estimator.cpql import CPQLEstimate, estimate_cpql
from estimator.estimator import EstimatorConfig, compute_estimates
from estimator.maturity import MaturityObservations, compute_maturity_observations

__all__ = [
    "compute_estimates",
    "EstimatorConfig",
    "estimate_rate",
    "BetaBinomialEstimate",
    "sample_posterior",
    "estimate_cpql",
    "CPQLEstimate",
    "compute_maturity_observations",
    "MaturityObservations",
]
