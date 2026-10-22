"""
Tests for empirical-Bayes hierarchical shrinkage and prior pooling.

Validates the requirements from docs/SPEC.md §3 and Step 3:
1. Method of moments fits Beta hyperparameters across portfolio/campaign ads.
2. Falls back to fixed prior when too few ads exist (< min_ads).
3. Minimum prior strength constraint stabilizes estimation under few ads or high variance.
4. Small samples shrink toward the portfolio mean (not the fixed prior mean).
5. Credible intervals narrow as data grows.
6. Pending and unreached leads never lower the qualification estimate q.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from domain.models import Advertisement, Lead, CallAttempt, QualificationOutcome
from domain.enums import LeadStatus, CallOutcome, QualificationResult
from estimator.shrinkage import fit_beta_prior_moments, EmpiricalBetaPrior
from estimator.estimator import (
    EstimatorConfig,
    compute_estimates,
    compute_campaign_estimates,
)


def test_fit_beta_prior_moments_fallback_when_few_ads():
    """When fewer than min_ads are available, fall back to fixed uninformative priors."""
    # Only 2 ads, min_ads=3
    obs = [(5, 10), (6, 10)]
    prior = fit_beta_prior_moments(
        observations=obs,
        fallback_alpha=1.0,
        fallback_beta=4.0,
        min_ads=3,
    )
    assert not prior.is_empirical
    assert prior.alpha == 1.0
    assert prior.beta == 4.0
    assert prior.mean == pytest.approx(0.20, abs=1e-3)


def test_fit_beta_prior_moments_minimum_prior_strength():
    """High variance or degenerate observations respect minimum prior strength."""
    # Extreme variance
    obs = [(0, 10), (10, 10), (0, 10), (10, 10)]
    prior = fit_beta_prior_moments(
        observations=obs,
        fallback_alpha=1.0,
        fallback_beta=1.0,
        min_ads=3,
        min_prior_strength=4.0,
    )
    assert prior.is_empirical
    assert prior.sample_size >= 4.0
    assert prior.alpha + prior.beta >= 4.0


def test_fit_beta_prior_moments_zero_variance_clamps_to_max_prior_strength():
    """When all ads have identical conversion rates, between-ad variance is zero, clamping kappa to max_prior_strength."""
    # 4 ads with identical 25% conversion rate
    obs = [(5, 20), (5, 20), (5, 20), (5, 20)]
    prior = fit_beta_prior_moments(
        observations=obs,
        fallback_alpha=1.0,
        fallback_beta=4.0,
        min_ads=3,
        min_prior_strength=4.0,
        max_prior_strength=50.0,
    )
    assert prior.is_empirical
    assert prior.mean == pytest.approx(0.25, abs=1e-4)
    assert prior.sample_size == 50.0
    assert prior.alpha == pytest.approx(12.5, abs=1e-4)
    assert prior.beta == pytest.approx(37.5, abs=1e-4)


def test_small_sample_shrinks_toward_portfolio_mean():
    """
    Prove that small samples shrink toward the portfolio mean, NOT the fixed prior mean.

    Setup:
      - 5 mature portfolio ads have high qualification rates (~50%).
      - Fixed uninformative prior for intent has mean = 1/(1+4) = 20%.
      - 1 new ad has a small sample: 2 trials, 0 qualified.
      - With fixed prior, the estimate shrinks toward 20% (giving ~1/7 = 14.3%).
      - With empirical-Bayes pooling, the estimate shrinks toward 50% (giving ~35-45%).
    """
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    config = EstimatorConfig(
        qualification_alpha_prior=1.0,
        qualification_beta_prior=4.0,  # 20% prior mean
    )

    # 5 mature ads with ~50% qualification rate
    ads_data = []
    for i in range(5):
        ad = Advertisement(
            id=f"ad_mature_{i}",
            ad_set_id="as1",
            creative_id=f"cr_{i}",
            spend=1000.0,
            impressions=20000,
            clicks=500,
        )
        leads = [
            Lead(id=f"l_m_{i}_{j}", advertisement_id=ad.id,
                 created_at=now - timedelta(days=12),
                 status=LeadStatus.SUBMITTED)
            for j in range(20)
        ]
        calls = [
            CallAttempt(id=f"c_m_{i}_{j}", lead_id=f"l_m_{i}_{j}",
                        attempted_at=now - timedelta(days=10),
                        outcome=CallOutcome.ANSWERED)
            for j in range(20)
        ]
        # 10 qualified out of 20 = 50% qualification rate
        quals = [
            QualificationOutcome(
                id=f"q_m_{i}_{j}", lead_id=f"l_m_{i}_{j}",
                resolved_at=now - timedelta(days=8),
                result=QualificationResult.QUALIFIED if j < 10 else QualificationResult.DISQUALIFIED,
            )
            for j in range(20)
        ]
        ads_data.append((ad, leads, calls, quals))

    # 6th ad: small sample with 2 trials, 0 qualified
    ad_small = Advertisement(
        id="ad_small",
        ad_set_id="as1",
        creative_id="cr_small",
        spend=100.0,
        impressions=2000,
        clicks=50,
    )
    leads_small = [
        Lead(id=f"l_s_{j}", advertisement_id=ad_small.id,
             created_at=now - timedelta(days=12),
             status=LeadStatus.SUBMITTED)
        for j in range(2)
    ]
    calls_small = [
        CallAttempt(id=f"c_s_{j}", lead_id=f"l_s_{j}",
                    attempted_at=now - timedelta(days=10),
                    outcome=CallOutcome.ANSWERED)
        for j in range(2)
    ]
    quals_small = [
        QualificationOutcome(
            id=f"q_s_{j}", lead_id=f"l_s_{j}",
            resolved_at=now - timedelta(days=8),
            result=QualificationResult.DISQUALIFIED,
        )
        for j in range(2)
    ]
    ads_data.append((ad_small, leads_small, calls_small, quals_small))

    # 1. Unpooled estimate (uses fixed prior Beta(1, 4), mean = 0.20)
    unpooled = compute_estimates(
        advertisement=ad_small,
        leads=leads_small,
        call_attempts=calls_small,
        qualification_outcomes=quals_small,
        observation_time=now,
        config=config,
    )

    # 2. Pooled empirical-Bayes estimates across campaign
    pooled_snapshots = compute_campaign_estimates(
        ads_data=ads_data,
        observation_time=now,
        config=config,
    )
    pooled_small = next(s for s in pooled_snapshots if s.advertisement_id == "ad_small")

    portfolio_mean = 0.50
    fixed_prior_mean = 0.20

    # Unpooled shrinks toward 0.20: (1 + 0) / (1 + 4 + 2) = 1/7 ≈ 0.143
    assert unpooled.qualification_mean == pytest.approx(1.0 / 7.0, abs=0.01)
    assert abs(unpooled.qualification_mean - fixed_prior_mean) < 0.10

    # Pooled must shrink toward portfolio mean (0.50), NOT the fixed prior mean (0.20)
    assert pooled_small.is_empirical_prior
    dist_to_portfolio = abs(pooled_small.qualification_mean - portfolio_mean)
    dist_to_fixed = abs(pooled_small.qualification_mean - fixed_prior_mean)

    assert dist_to_portfolio < dist_to_fixed, (
        f"Pooled estimate {pooled_small.qualification_mean:.3f} should be closer to "
        f"portfolio mean ({portfolio_mean}) than fixed prior mean ({fixed_prior_mean})"
    )
    assert pooled_small.qualification_mean > 0.30


def test_credible_intervals_narrow_as_data_grows():
    """Verify that credible interval width strictly narrows as mature sample size increases."""
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    config = EstimatorConfig()

    sample_sizes = [5, 20, 100]
    ci_widths = []

    for n in sample_sizes:
        ad = Advertisement(
            id=f"ad_sample_{n}",
            ad_set_id="as1",
            creative_id=f"cr_{n}",
            spend=float(n * 20),
            impressions=n * 200,
            clicks=n * 5,
        )
        leads = [
            Lead(id=f"l_{n}_{i}", advertisement_id=ad.id,
                 created_at=now - timedelta(days=12),
                 status=LeadStatus.SUBMITTED)
            for i in range(n)
        ]
        calls = [
            CallAttempt(id=f"c_{n}_{i}", lead_id=f"l_{n}_{i}",
                        attempted_at=now - timedelta(days=10),
                        outcome=CallOutcome.ANSWERED)
            for i in range(n)
        ]
        # Fixed 30% qualified
        k = int(round(n * 0.30))
        quals = [
            QualificationOutcome(
                id=f"q_{n}_{i}", lead_id=f"l_{n}_{i}",
                resolved_at=now - timedelta(days=8),
                result=QualificationResult.QUALIFIED if i < k else QualificationResult.DISQUALIFIED,
            )
            for i in range(n)
        ]
        snap = compute_estimates(
            advertisement=ad,
            leads=leads,
            call_attempts=calls,
            qualification_outcomes=quals,
            observation_time=now,
            config=config,
            seed=42,
        )
        ci_width = snap.qualification_ci_high - snap.qualification_ci_low
        ci_widths.append(ci_width)

    # Monotonically strictly decreasing interval width
    assert ci_widths[0] > ci_widths[1] > ci_widths[2], (
        f"Interval widths should narrow: {ci_widths}"
    )


def test_pending_and_unreached_leads_never_lower_q():
    """
    Verify that unreached and pending leads never lower the qualification estimate q.

    Because q is conditioned on mature contacts, arriving leads that are either
    unreached or within the qualification maturity window must not enter the
    denominator of the qualification rate estimator.
    """
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    config = EstimatorConfig(
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
    )

    ad = Advertisement(
        id="ad_maturity_test",
        ad_set_id="as1",
        creative_id="cr_mat",
        spend=500.0,
        impressions=10000,
        clicks=200,
    )

    # Initial mature leads: 10 reached, 4 qualified
    leads = [
        Lead(id=f"l_init_{i}", advertisement_id=ad.id,
             created_at=now - timedelta(days=15),
             status=LeadStatus.SUBMITTED)
        for i in range(10)
    ]
    calls = [
        CallAttempt(id=f"c_init_{i}", lead_id=f"l_init_{i}",
                    attempted_at=now - timedelta(days=12),
                    outcome=CallOutcome.ANSWERED)
        for i in range(10)
    ]
    quals = [
        QualificationOutcome(
            id=f"q_init_{i}", lead_id=f"l_init_{i}",
            resolved_at=now - timedelta(days=10),
            result=QualificationResult.QUALIFIED if i < 4 else QualificationResult.DISQUALIFIED,
        )
        for i in range(10)
    ]

    base_snapshot = compute_estimates(
        advertisement=ad,
        leads=leads,
        call_attempts=calls,
        qualification_outcomes=quals,
        observation_time=now,
        config=config,
        seed=100,
    )
    base_q = base_snapshot.qualification_mean
    base_mature_contacts = base_snapshot.n_mature_contacts

    # 1. Add 50 UNREACHED leads (submitted 1 day ago, no call attempt)
    unreached_leads = [
        Lead(id=f"l_unreached_{i}", advertisement_id=ad.id,
             created_at=now - timedelta(days=1),
             status=LeadStatus.SUBMITTED)
        for i in range(50)
    ]
    snap_with_unreached = compute_estimates(
        advertisement=ad,
        leads=leads + unreached_leads,
        call_attempts=calls,
        qualification_outcomes=quals,
        observation_time=now,
        config=config,
        seed=100,
    )
    assert snap_with_unreached.n_mature_contacts == base_mature_contacts
    assert snap_with_unreached.qualification_mean == base_q, (
        "Unreached leads must not change or lower qualification rate q"
    )

    # 2. Add 50 PENDING leads (contacted 2 days ago, within 7-day qualification window, unresolved)
    pending_leads = [
        Lead(id=f"l_pending_{i}", advertisement_id=ad.id,
             created_at=now - timedelta(days=3),
             status=LeadStatus.SUBMITTED)
        for i in range(50)
    ]
    pending_calls = [
        CallAttempt(id=f"c_pending_{i}", lead_id=f"l_pending_{i}",
                    attempted_at=now - timedelta(days=2),
                    outcome=CallOutcome.ANSWERED)
        for i in range(50)
    ]
    # No qualification outcome yet (pending)
    snap_with_pending = compute_estimates(
        advertisement=ad,
        leads=leads + unreached_leads + pending_leads,
        call_attempts=calls + pending_calls,
        qualification_outcomes=quals,
        observation_time=now,
        config=config,
        seed=100,
    )
    assert snap_with_pending.n_mature_contacts == base_mature_contacts
    assert snap_with_pending.qualification_mean == base_q, (
        "Pending leads must not change or lower qualification rate q"
    )
