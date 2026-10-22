"""Estimator package."""

from estimator.beta_binomial import BetaBinomialEstimate, estimate_rate, sample_posterior
from estimator.cpql import CPQLEstimate, estimate_cpql
from estimator.estimator import EstimatorConfig, compute_campaign_estimates, compute_estimates
from estimator.maturity import MaturityObservations, compute_maturity_observations
from estimator.shrinkage import EmpiricalBetaPrior, fit_beta_prior_moments

__all__ = [
    "compute_estimates",
    "compute_campaign_estimates",
    "EstimatorConfig",
    "estimate_rate",
    "BetaBinomialEstimate",
    "sample_posterior",
    "estimate_cpql",
    "CPQLEstimate",
    "compute_maturity_observations",
    "MaturityObservations",
    "fit_beta_prior_moments",
    "EmpiricalBetaPrior",
]
