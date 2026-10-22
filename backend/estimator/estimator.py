"""
Main estimator entry point.

Coordinates maturity computation, Beta-Binomial estimation, and CPQL
to produce a complete EstimateSnapshot for a given advertisement.

This module has NO dependency on FastAPI, SQLAlchemy, or the simulator.
It receives plain domain objects and returns a plain domain object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from domain.models import (
    Advertisement,
    CallAttempt,
    EstimateSnapshot,
    Lead,
    QualificationOutcome,
)
from estimator.beta_binomial import derive_rng, estimate_rate
from estimator.cpql import estimate_cpql
from estimator.maturity import compute_maturity_observations
from estimator.shrinkage import fit_beta_prior_moments

ESTIMATOR_VERSION = "0.1.0"

# Prior parameters
REACHABILITY_ALPHA_PRIOR = 1.0
REACHABILITY_BETA_PRIOR = 1.0  # uniform — no preference

QUALIFICATION_ALPHA_PRIOR = 1.0
QUALIFICATION_BETA_PRIOR = 4.0  # encodes ~20% expected qualification rate

# Evidence sufficiency thresholds
MIN_MATURE_LEADS = 30
MIN_MATURE_CONTACTS = 20
MIN_MATURITY_FRACTION = 0.60

CI_LEVEL = 0.90
MONTE_CARLO_SAMPLES = 10_000


@dataclass
class EstimatorConfig:
    """Configuration for the estimator — all thresholds in one place."""

    contact_maturity_days: float = 3.0
    qualification_maturity_days: float = 7.0
    min_mature_leads: int = MIN_MATURE_LEADS
    min_mature_contacts: int = MIN_MATURE_CONTACTS
    min_maturity_fraction: float = MIN_MATURITY_FRACTION
    ci_level: float = CI_LEVEL
    monte_carlo_samples: int = MONTE_CARLO_SAMPLES
    reachability_alpha_prior: float = REACHABILITY_ALPHA_PRIOR
    reachability_beta_prior: float = REACHABILITY_BETA_PRIOR
    qualification_alpha_prior: float = QUALIFICATION_ALPHA_PRIOR
    qualification_beta_prior: float = QUALIFICATION_BETA_PRIOR


def compute_estimates(
    advertisement: Advertisement,
    leads: list[Lead],
    call_attempts: list[CallAttempt],
    qualification_outcomes: list[QualificationOutcome],
    observation_time: datetime | None = None,
    config: EstimatorConfig | None = None,
    rng: np.random.Generator | None = None,
    seed: int | None = None,
    reachability_prior: tuple[float, float] | None = None,
    qualification_prior: tuple[float, float] | None = None,
    is_empirical_prior: bool = False,
) -> EstimateSnapshot:
    """
    Compute a full estimate snapshot for one advertisement.

    Args:
        advertisement: The ad being estimated
        leads: All leads attributed to this ad
        call_attempts: All call attempts for these leads
        qualification_outcomes: All resolved qualification outcomes
        observation_time: Reference "now" — defaults to current UTC time
        config: Estimator configuration (defaults to EstimatorConfig())
        rng: Optional numpy random generator for reproducibility
        seed: Optional run seed to derive deterministic RNG from (seed, ad_id)
        reachability_prior: Optional (alpha, beta) for reachability (e.g. from empirical Bayes)
        qualification_prior: Optional (alpha, beta) for qualification (e.g. from empirical Bayes)
        is_empirical_prior: True if using fitted empirical Bayes priors across ads

    Returns:
        EstimateSnapshot with all estimates and uncertainty intervals

    Architecture guarantee: This function does not access hidden ground truth.
    It receives only observable domain objects.
    """
    if observation_time is None:
        observation_time = datetime.now(timezone.utc)
    if config is None:
        config = EstimatorConfig()
    if rng is None:
        rng = derive_rng(seed, advertisement.id)

    # Resolve priors (empirical if provided, else fallback to config fixed priors)
    r_alpha = reachability_prior[0] if reachability_prior is not None else config.reachability_alpha_prior
    r_beta = reachability_prior[1] if reachability_prior is not None else config.reachability_beta_prior

    q_alpha = qualification_prior[0] if qualification_prior is not None else config.qualification_alpha_prior
    q_beta = qualification_prior[1] if qualification_prior is not None else config.qualification_beta_prior

    # Step 1: Compute maturity-respecting observation counts
    obs = compute_maturity_observations(
        leads=leads,
        call_attempts=call_attempts,
        qualification_outcomes=qualification_outcomes,
        observation_time=observation_time,
        contact_maturity_days=config.contact_maturity_days,
        qualification_maturity_days=config.qualification_maturity_days,
    )

    # Step 2: Estimate reachability
    reach_est = estimate_rate(
        n=obs.n_mature_leads,
        k=obs.k_contacted,
        alpha_prior=r_alpha,
        beta_prior=r_beta,
        ci_level=config.ci_level,
    )

    # Step 3: Estimate qualification rate
    qual_est = estimate_rate(
        n=obs.n_mature_contacts,
        k=obs.k_qualified,
        alpha_prior=q_alpha,
        beta_prior=q_beta,
        ci_level=config.ci_level,
    )

    # Step 4: Compute maturity fractions
    maturity_fraction_contact = (
        obs.n_mature_leads / obs.n_leads if obs.n_leads > 0 else 0.0
    )
    maturity_fraction_qualification = (
        obs.n_mature_contacts / obs.n_contacts if obs.n_contacts > 0 else 0.0
    )

    # Step 5: Evidence sufficiency flags
    evidence_sufficient_reachability = (
        obs.n_mature_leads >= config.min_mature_leads
        and maturity_fraction_contact >= config.min_maturity_fraction
    )
    evidence_sufficient_qualification = (
        obs.n_mature_contacts >= config.min_mature_contacts
    )

    # Step 6: CPQL estimation via Monte Carlo
    cpql = estimate_cpql(
        spend=advertisement.spend,
        n_leads=float(obs.n_leads),
        maturity_fraction=maturity_fraction_contact,
        reachability_estimate=reach_est,
        qualification_estimate=qual_est,
        n_samples=config.monte_carlo_samples,
        ci_level=config.ci_level,
        rng=rng,
    )

    return EstimateSnapshot(
        advertisement_id=advertisement.id,
        computed_at=observation_time,
        estimator_version=ESTIMATOR_VERSION,
        n_leads=obs.n_leads,
        n_mature_leads=obs.n_mature_leads,
        n_contacts=obs.n_contacts,
        n_mature_contacts=obs.n_mature_contacts,
        k_qualified=obs.k_qualified,
        maturity_fraction_contact=maturity_fraction_contact,
        maturity_fraction_qualification=maturity_fraction_qualification,
        reachability_mean=reach_est.posterior_mean,
        reachability_ci_low=reach_est.ci_low,
        reachability_ci_high=reach_est.ci_high,
        qualification_mean=qual_est.posterior_mean,
        qualification_ci_low=qual_est.ci_low,
        qualification_ci_high=qual_est.ci_high,
        eql_mean=cpql.eql_mean,
        eql_ci_low=cpql.eql_ci_low,
        eql_ci_high=cpql.eql_ci_high,
        cpql_mean=cpql.cpql_mean,
        cpql_ci_low=cpql.cpql_ci_low,
        cpql_ci_high=cpql.cpql_ci_high,
        cpql_unstable=cpql.unstable,
        evidence_sufficient_reachability=evidence_sufficient_reachability,
        evidence_sufficient_qualification=evidence_sufficient_qualification,
        zero_eql_fraction=cpql.zero_eql_fraction,
        reachability_prior_alpha=r_alpha,
        reachability_prior_beta=r_beta,
        qualification_prior_alpha=q_alpha,
        qualification_prior_beta=q_beta,
        is_empirical_prior=is_empirical_prior,
    )


def compute_campaign_estimates(
    ads_data: list[tuple[Advertisement, list[Lead], list[CallAttempt], list[QualificationOutcome]]],
    observation_time: datetime | None = None,
    config: EstimatorConfig | None = None,
    seed: int | None = None,
    min_ads_for_shrinkage: int = 3,
    enable_shrinkage: bool = True,
) -> list[EstimateSnapshot]:
    """
    Compute estimates for an entire campaign or portfolio of ads using
    empirical-Bayes shrinkage across the ads.

    Fits Beta hyperparameters for reachability (r) and intent (q) via Method
    of Moments across the campaign ads, maintaining minimum prior strength
    constraints and automatically falling back to fixed priors when fewer than
    min_ads_for_shrinkage ads have sufficient data.

    Args:
        ads_data: List of (ad, leads, call_attempts, qualification_outcomes)
        observation_time: Observation timestamp
        config: EstimatorConfig
        seed: Random seed for deterministic simulation/estimation
        min_ads_for_shrinkage: Minimum ads with data required to fit empirical priors
        enable_shrinkage: If False, disables empirical pooling and uses fixed priors for ablation

    Returns:
        List of EstimateSnapshot corresponding to the input ads_data order
    """
    if observation_time is None:
        observation_time = datetime.now(timezone.utc)
    if config is None:
        config = EstimatorConfig()

    if not enable_shrinkage:
        reach_alpha = config.reachability_alpha_prior
        reach_beta = config.reachability_beta_prior
        qual_alpha = config.qualification_alpha_prior
        qual_beta = config.qualification_beta_prior
        reach_prior_empirical = False
        qual_prior_empirical = False
    else:
        # Precompute maturity observations to extract empirical rates
        reach_obs: list[tuple[int, int]] = []
        qual_obs: list[tuple[int, int]] = []

        for ad, leads, call_attempts, qual_outcomes in ads_data:
            obs = compute_maturity_observations(
                leads=leads,
                call_attempts=call_attempts,
                qualification_outcomes=qual_outcomes,
                observation_time=observation_time,
                contact_maturity_days=config.contact_maturity_days,
                qualification_maturity_days=config.qualification_maturity_days,
            )
            reach_obs.append((obs.k_contacted, obs.n_mature_leads))
            qual_obs.append((obs.k_qualified, obs.n_mature_contacts))

        # Fit empirical priors via Method of Moments across the campaign
        reach_prior = fit_beta_prior_moments(
            observations=reach_obs,
            fallback_alpha=config.reachability_alpha_prior,
            fallback_beta=config.reachability_beta_prior,
            min_ads=min_ads_for_shrinkage,
        )
        qual_prior = fit_beta_prior_moments(
            observations=qual_obs,
            fallback_alpha=config.qualification_alpha_prior,
            fallback_beta=config.qualification_beta_prior,
            min_ads=min_ads_for_shrinkage,
        )
        reach_alpha, reach_beta = reach_prior.alpha, reach_prior.beta
        qual_alpha, qual_beta = qual_prior.alpha, qual_prior.beta
        reach_prior_empirical = reach_prior.is_empirical
        qual_prior_empirical = qual_prior.is_empirical

    snapshots: list[EstimateSnapshot] = []
    for ad, leads, call_attempts, qual_outcomes in ads_data:
        snap = compute_estimates(
            advertisement=ad,
            leads=leads,
            call_attempts=call_attempts,
            qualification_outcomes=qual_outcomes,
            observation_time=observation_time,
            config=config,
            seed=seed,
            reachability_prior=(reach_alpha, reach_beta),
            qualification_prior=(qual_alpha, qual_beta),
            is_empirical_prior=reach_prior_empirical or qual_prior_empirical,
        )
        snapshots.append(snap)

    return snapshots

