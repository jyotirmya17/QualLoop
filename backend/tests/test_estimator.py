"""
Tests for the statistical estimator.

Tests verify all edge cases specified in docs/STATISTICAL_MODEL.md §9:
- Zero observations return prior distribution
- One observation is handled correctly
- Small samples produce wide credible intervals
- All qualified / no qualified outcomes
- Pending leads are not counted as failures
- Unreachable leads inform reachability but not qualification
- Very low qualification probability
- Credible intervals always contain the mean
- Maturity window boundaries
- Invalid inputs are rejected
"""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from estimator.beta_binomial import estimate_rate, BetaBinomialEstimate, sample_posterior
from estimator.maturity import compute_maturity_observations
from estimator.cpql import estimate_cpql
from estimator.estimator import compute_estimates, EstimatorConfig


# ---------------------------------------------------------------------------
# Beta-Binomial model tests
# ---------------------------------------------------------------------------

class TestBetaBinomialModel:
    def test_zero_observations_returns_prior(self):
        est = estimate_rate(n=0, k=0, alpha_prior=1.0, beta_prior=1.0)
        # With uniform prior Beta(1,1), posterior mean = 1/(1+1) = 0.5
        assert abs(est.posterior_mean - 0.5) < 1e-9
        assert est.has_data is False

    def test_one_success_one_trial(self):
        est = estimate_rate(n=1, k=1, alpha_prior=1.0, beta_prior=1.0)
        # Posterior Beta(2, 1): mean = 2/3
        assert abs(est.posterior_mean - 2 / 3) < 1e-9

    def test_one_failure_one_trial(self):
        est = estimate_rate(n=1, k=0, alpha_prior=1.0, beta_prior=1.0)
        # Posterior Beta(1, 2): mean = 1/3
        assert abs(est.posterior_mean - 1 / 3) < 1e-9

    def test_all_successes_large_sample(self):
        est = estimate_rate(n=100, k=100, alpha_prior=1.0, beta_prior=1.0)
        # Posterior Beta(101, 1): mean = 101/102 ≈ 0.99
        assert est.posterior_mean > 0.95
        assert est.ci_low > 0.90

    def test_no_successes_large_sample(self):
        est = estimate_rate(n=100, k=0, alpha_prior=1.0, beta_prior=1.0)
        # Posterior Beta(1, 101): mean = 1/102 ≈ 0.0098
        assert est.posterior_mean < 0.05
        assert est.ci_high < 0.10

    def test_ci_contains_mean(self):
        for k, n in [(0, 0), (0, 10), (5, 10), (10, 10), (50, 100)]:
            est = estimate_rate(n=n, k=k)
            assert est.ci_low <= est.posterior_mean <= est.ci_high, (
                f"CI [{est.ci_low}, {est.ci_high}] does not contain mean "
                f"{est.posterior_mean} for n={n}, k={k}"
            )

    def test_small_sample_produces_wide_ci(self):
        small = estimate_rate(n=5, k=2)
        large = estimate_rate(n=500, k=200)
        small_width = small.ci_high - small.ci_low
        large_width = large.ci_high - large.ci_low
        assert small_width > large_width, (
            "Small sample should produce wider credible interval than large sample"
        )

    def test_informative_prior_shrinks_toward_prior_mean(self):
        # Prior Beta(1, 4): mean = 1/5 = 0.2
        # With 1 observation (1 success), posterior should be closer to 0.2 than 1.0
        est = estimate_rate(n=1, k=1, alpha_prior=1.0, beta_prior=4.0)
        assert est.posterior_mean < 0.6, "Informative prior should shrink toward 0.2"

    def test_invalid_k_greater_than_n(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            estimate_rate(n=5, k=6)

    def test_invalid_negative_n(self):
        with pytest.raises(ValueError, match=">= 0"):
            estimate_rate(n=-1, k=0)

    def test_invalid_negative_k(self):
        with pytest.raises(ValueError, match=">= 0"):
            estimate_rate(n=5, k=-1)

    def test_invalid_alpha_prior(self):
        with pytest.raises(ValueError, match="alpha_prior"):
            estimate_rate(n=5, k=2, alpha_prior=0.0)

    def test_invalid_ci_level(self):
        with pytest.raises(ValueError, match="ci_level"):
            estimate_rate(n=5, k=2, ci_level=1.5)

    def test_posterior_samples_are_in_unit_interval(self):
        est = estimate_rate(n=50, k=20)
        rng = np.random.default_rng(42)
        samples = sample_posterior(est, n_samples=1000, rng=rng)
        assert np.all(samples >= 0.0)
        assert np.all(samples <= 1.0)

    def test_posterior_samples_mean_matches_estimate(self):
        est = estimate_rate(n=100, k=40)
        rng = np.random.default_rng(42)
        samples = sample_posterior(est, n_samples=50_000, rng=rng)
        assert abs(np.mean(samples) - est.posterior_mean) < 0.01


# ---------------------------------------------------------------------------
# Maturity window tests
# ---------------------------------------------------------------------------

class TestMaturityObservations:
    """Tests for correct denominator computation with maturity windows."""

    def _make_lead(self, lead_id: str, ad_id: str, created_at: datetime):
        from domain.models import Lead
        from domain.enums import LeadStatus
        return Lead(
            id=lead_id,
            advertisement_id=ad_id,
            created_at=created_at,
            status=LeadStatus.SUBMITTED,
        )

    def _make_call(self, call_id: str, lead_id: str, at: datetime, outcome):
        from domain.models import CallAttempt
        return CallAttempt(id=call_id, lead_id=lead_id, attempted_at=at, outcome=outcome)

    def _make_qual(self, qual_id: str, lead_id: str, at: datetime, result):
        from domain.models import QualificationOutcome
        return QualificationOutcome(
            id=qual_id, lead_id=lead_id, resolved_at=at, result=result
        )

    def test_pending_leads_excluded_from_reachability_denominator(self):
        """Leads inside the contact maturity window must not count in n_mature_leads."""
        from domain.enums import CallOutcome
        now = datetime(2025, 1, 10, tzinfo=timezone.utc)
        # Lead created 1 day ago — inside 3-day maturity window
        lead = self._make_lead("l1", "ad1", created_at=now - timedelta(days=1))

        obs = compute_maturity_observations(
            leads=[lead],
            call_attempts=[],
            qualification_outcomes=[],
            observation_time=now,
            contact_maturity_days=3.0,
        )
        assert obs.n_mature_leads == 0, "Lead inside maturity window should not be in denominator"
        assert obs.n_pending_contact == 1

    def test_mature_unreachable_lead_is_in_denominator(self):
        """A mature lead with no successful contact is in reachability denominator (as failure)."""
        from domain.enums import CallOutcome
        now = datetime(2025, 1, 10, tzinfo=timezone.utc)
        lead = self._make_lead("l1", "ad1", created_at=now - timedelta(days=5))
        # No successful call
        call = self._make_call("c1", "l1", now - timedelta(days=4), CallOutcome.NO_ANSWER)

        obs = compute_maturity_observations(
            leads=[lead],
            call_attempts=[call],
            qualification_outcomes=[],
            observation_time=now,
        )
        assert obs.n_mature_leads == 1
        assert obs.k_contacted == 0  # not counted as success

    def test_unreachable_lead_not_in_qualification_denominator(self):
        """A lead that was never contacted must not affect qualification estimates."""
        from domain.enums import CallOutcome
        now = datetime(2025, 1, 10, tzinfo=timezone.utc)
        lead = self._make_lead("l1", "ad1", created_at=now - timedelta(days=5))
        call = self._make_call("c1", "l1", now - timedelta(days=4), CallOutcome.NO_ANSWER)

        obs = compute_maturity_observations(
            leads=[lead], call_attempts=[call], qualification_outcomes=[], observation_time=now
        )
        assert obs.n_mature_contacts == 0, (
            "Unreachable lead must not contribute to qualification denominator"
        )

    def test_pending_qualification_excluded_from_intent_denominator(self):
        """A contact inside the qualification window must not count in n_mature_contacts."""
        from domain.enums import CallOutcome, QualificationResult
        now = datetime(2025, 1, 10, tzinfo=timezone.utc)
        lead = self._make_lead("l1", "ad1", created_at=now - timedelta(days=10))
        # Contacted 1 day ago — inside 7-day qualification window
        call = self._make_call("c1", "l1", now - timedelta(days=1), CallOutcome.ANSWERED)
        qual = self._make_qual("q1", "l1", now - timedelta(hours=6), QualificationResult.QUALIFIED)

        obs = compute_maturity_observations(
            leads=[lead],
            call_attempts=[call],
            qualification_outcomes=[qual],
            observation_time=now,
            qualification_maturity_days=7.0,
        )
        assert obs.n_mature_contacts == 0, (
            "Contact inside qualification window should not be in denominator"
        )

    def test_qualified_contact_after_maturity_counts(self):
        """A qualified contact past the qualification window should count correctly."""
        from domain.enums import CallOutcome, QualificationResult
        now = datetime(2025, 1, 10, tzinfo=timezone.utc)
        lead = self._make_lead("l1", "ad1", created_at=now - timedelta(days=20))
        call = self._make_call("c1", "l1", now - timedelta(days=10), CallOutcome.ANSWERED)
        qual = self._make_qual("q1", "l1", now - timedelta(days=8), QualificationResult.QUALIFIED)

        obs = compute_maturity_observations(
            leads=[lead],
            call_attempts=[call],
            qualification_outcomes=[qual],
            observation_time=now,
        )
        assert obs.n_mature_contacts == 1
        assert obs.k_qualified == 1

    def test_disqualified_contact_reduces_denominator_not_numerator(self):
        """A disqualified contact should be in denominator but not numerator."""
        from domain.enums import CallOutcome, QualificationResult
        now = datetime(2025, 1, 10, tzinfo=timezone.utc)
        lead = self._make_lead("l1", "ad1", created_at=now - timedelta(days=20))
        call = self._make_call("c1", "l1", now - timedelta(days=10), CallOutcome.ANSWERED)
        qual = self._make_qual("q1", "l1", now - timedelta(days=8), QualificationResult.DISQUALIFIED)

        obs = compute_maturity_observations(
            leads=[lead], call_attempts=[call], qualification_outcomes=[qual], observation_time=now
        )
        assert obs.n_mature_contacts == 1
        assert obs.k_qualified == 0


# ---------------------------------------------------------------------------
# CPQL estimator tests
# ---------------------------------------------------------------------------

class TestCPQLEstimator:
    def _make_estimate(self, n, k, alpha=1.0, beta=1.0):
        return estimate_rate(n=n, k=k, alpha_prior=alpha, beta_prior=beta)

    def test_zero_leads_returns_unstable(self):
        reach = self._make_estimate(0, 0)
        qual = self._make_estimate(0, 0)
        result = estimate_cpql(
            spend=1000.0, n_leads=0, maturity_fraction=1.0,
            reachability_estimate=reach, qualification_estimate=qual,
        )
        assert result.unstable is True
        assert result.cpql_mean is None

    def test_zero_spend_returns_no_cpql(self):
        reach = self._make_estimate(50, 30)
        qual = self._make_estimate(20, 5)
        result = estimate_cpql(
            spend=0.0, n_leads=50, maturity_fraction=1.0,
            reachability_estimate=reach, qualification_estimate=qual,
        )
        assert result.cpql_mean is None

    def test_high_qualification_gives_reasonable_cpql(self):
        reach = self._make_estimate(100, 70)  # 70% reachability
        qual = self._make_estimate(60, 30)    # 50% qualification
        rng = np.random.default_rng(42)
        result = estimate_cpql(
            spend=5000.0, n_leads=100, maturity_fraction=1.0,
            reachability_estimate=reach, qualification_estimate=qual, rng=rng,
        )
        assert result.cpql_mean is not None
        assert result.cpql_mean > 0
        assert result.unstable is False
        # EQL ≈ 100 * 1.0 * 0.7 * 0.5 = 35 → CPQL ≈ 5000/35 ≈ 143
        assert 50 < result.cpql_mean < 500

    def test_eql_ci_is_wider_with_small_sample(self):
        reach_small = self._make_estimate(5, 3)
        qual_small = self._make_estimate(3, 1)
        reach_large = self._make_estimate(500, 300)
        qual_large = self._make_estimate(200, 80)

        rng = np.random.default_rng(42)
        small = estimate_cpql(
            spend=1000.0, n_leads=10, maturity_fraction=1.0,
            reachability_estimate=reach_small, qualification_estimate=qual_small,
            n_samples=10_000, rng=rng,
        )
        large = estimate_cpql(
            spend=50000.0, n_leads=500, maturity_fraction=1.0,
            reachability_estimate=reach_large, qualification_estimate=qual_large,
            n_samples=10_000, rng=rng,
        )
        small_eql_width = small.eql_ci_high - small.eql_ci_low
        large_eql_width = large.eql_ci_high - large.eql_ci_low

        # Width should be larger for small relative to EQL magnitude
        small_relative_width = small_eql_width / (small.eql_mean + 1e-9)
        large_relative_width = large_eql_width / (large.eql_mean + 1e-9)
        assert small_relative_width > large_relative_width

    def test_cpql_jensens_inequality_guarantee(self):
        """
        Prove Jensen's inequality: because f(x) = spend / x is strictly convex for x > 0,
        the posterior expectation E[spend / EQL] must strictly exceed the plug-in ratio spend / E[EQL]
        whenever there is posterior parameter uncertainty.
        """
        reach = self._make_estimate(40, 25)
        qual = self._make_estimate(25, 10)
        rng = np.random.default_rng(12345)

        spend = 3000.0
        res = estimate_cpql(
            spend=spend,
            n_leads=80,
            maturity_fraction=1.0,
            reachability_estimate=reach,
            qualification_estimate=qual,
            n_samples=20_000,
            rng=rng,
        )

        assert res.cpql_mean is not None
        assert res.eql_mean > 0

        plug_in_ratio = spend / res.eql_mean
        posterior_mean_cpql = res.cpql_mean

        # Jensen's inequality: E[spend/EQL] > spend / E[EQL]
        assert posterior_mean_cpql > plug_in_ratio, (
            f"Posterior expectation {posterior_mean_cpql:.2f} must strictly exceed "
            f"plug-in ratio of means {plug_in_ratio:.2f} due to Jensen's inequality."
        )

        # Both CI bounds and mean are derived from identical posterior distribution
        assert res.cpql_ci_low is not None and res.cpql_ci_high is not None
        assert res.cpql_ci_low < posterior_mean_cpql < res.cpql_ci_high

    def test_cpql_snapshot_scenario_reproduction(self):
        """
        Deterministically reproduce and verify the audit example:
        Spend: $3,000, eql_mean ≈ 19.96 - 20.11, cpql_mean ≈ 156.44 - 157.47, cpql_ci ≈ [109.5, 223.1].
        Demonstrates that cpql_mean ≈ $157 vs spend/eql_mean ≈ $150.30 is due to the convex
        transformation of posterior samples (Jensen's inequality), not an arithmetic error.
        """
        # Reachability: 50 / 70 contacted
        reach = estimate_rate(n=70, k=50, alpha_prior=1.0, beta_prior=1.0)
        # Qualification: 14 / 35 qualified
        qual = estimate_rate(n=35, k=14, alpha_prior=1.0, beta_prior=1.0)

        rng = np.random.default_rng(42)
        res = estimate_cpql(
            spend=3000.0,
            n_leads=70,
            maturity_fraction=1.0,
            reachability_estimate=reach,
            qualification_estimate=qual,
            n_samples=10_000,
            rng=rng,
        )

        # EQL mean is ~ 20.11 (target ~ 19.96 - 20.11)
        assert abs(res.eql_mean - 20.0) < 0.50
        # Plug-in ratio spend / eql_mean is ~ $149 - $150
        plug_in = 3000.0 / res.eql_mean
        assert abs(plug_in - 150.0) < 5.0

        # Posterior mean CPQL is ~ $156.44 - $157.50
        assert abs(res.cpql_mean - 157.0) < 3.0
        # Credible interval spans ~ [109.5, 223.1]
        assert abs(res.cpql_ci_low - 109.5) < 3.0
        assert abs(res.cpql_ci_high - 223.1) < 3.0

        # Unstable is False and zero_eql_fraction is 0.0
        assert res.unstable is False
        assert res.zero_eql_fraction == 0.0

    def test_cpql_zero_and_near_zero_leads_handling(self):
        """Verify zero-denominator, high zero-fraction, and numerical stability behavior."""
        reach = self._make_estimate(10, 1)  # very low reachability
        qual = self._make_estimate(5, 0)   # 0 qualified leads

        rng = np.random.default_rng(42)
        # 1 lead with tiny rates -> virtually all draws have EQL < 0.5
        res = estimate_cpql(
            spend=500.0,
            n_leads=1,
            maturity_fraction=0.5,
            reachability_estimate=reach,
            qualification_estimate=qual,
            n_samples=5_000,
            rng=rng,
        )
        assert res.zero_eql_fraction > 0.90
        assert res.unstable is True

    def test_cpql_negative_spend_rejected(self):
        """Negative spend must produce degenerate unstable estimate without crash."""
        reach = self._make_estimate(50, 30)
        qual = self._make_estimate(20, 5)
        res = estimate_cpql(
            spend=-500.0,
            n_leads=50,
            maturity_fraction=1.0,
            reachability_estimate=reach,
            qualification_estimate=qual,
        )
        assert res.cpql_mean is None
        assert res.unstable is True
        assert res.zero_eql_fraction == 1.0

    def test_cpql_maturity_fraction_scales_spend_consistently(self):
        """
        Verify that maturity_fraction scales both leads (in EQL) and spend (in CPQL numerator)
        consistently, so that CPQL estimates remain unbiased across cohorts with varying maturity.
        """
        reach = self._make_estimate(100, 70)
        qual = self._make_estimate(70, 35)

        # Baseline: 100 leads, $5000 spend, 100% mature
        rng_full = np.random.default_rng(999)
        full_mature = estimate_cpql(
            spend=5000.0,
            n_leads=100,
            maturity_fraction=1.0,
            reachability_estimate=reach,
            qualification_estimate=qual,
            n_samples=10_000,
            rng=rng_full,
        )

        # 50% mature: 100 leads, $5000 total spend, maturity_fraction=0.5
        # Under consistent scaling, effective_spend = $2500 and mature_leads = 50.
        # CPQL = $2500 / (50 * p_r * p_q) == $5000 / (100 * p_r * p_q).
        rng_half = np.random.default_rng(999)
        half_mature = estimate_cpql(
            spend=5000.0,
            n_leads=100,
            maturity_fraction=0.5,
            reachability_estimate=reach,
            qualification_estimate=qual,
            n_samples=10_000,
            rng=rng_half,
        )

        # The EQL for half_mature is half of full_mature
        assert abs(half_mature.eql_mean - (full_mature.eql_mean * 0.5)) < 0.1
        # CPQL should be virtually identical because effective spend is also halved
        assert half_mature.cpql_mean is not None
        assert full_mature.cpql_mean is not None
        assert abs(half_mature.cpql_mean - full_mature.cpql_mean) < 1.0

    def test_cpql_reports_median_and_truncated_mean(self):
        """Verify that CPQLEstimate reports both truncated conditional mean and median."""
        reach = self._make_estimate(80, 50)
        qual = self._make_estimate(50, 20)
        res = estimate_cpql(
            spend=4000.0,
            n_leads=80,
            maturity_fraction=1.0,
            reachability_estimate=reach,
            qualification_estimate=qual,
            seed=42,
        )
        assert res.cpql_mean is not None
        assert res.cpql_median is not None
        assert res.is_truncated_mean is True
        # Due to positive skew of 1/x, mean CPQL >= median CPQL
        assert res.cpql_mean >= res.cpql_median



# ---------------------------------------------------------------------------
# Full compute_estimates integration test
# ---------------------------------------------------------------------------

class TestComputeEstimates:
    def test_compute_estimates_basic(self):
        """Full integration test using a small synthetic dataset."""
        from domain.enums import CallOutcome, QualificationResult, LeadStatus
        from domain.models import Advertisement, Lead, CallAttempt, QualificationOutcome
        from datetime import timedelta

        now = datetime(2025, 2, 1, tzinfo=timezone.utc)
        ad = Advertisement(
            id="ad1", ad_set_id="as1", creative_id="creative1",
            spend=5000.0, impressions=50000, clicks=2000,
        )

        # Create 40 leads, all mature (created 10 days ago)
        leads = [
            Lead(id=f"l{i}", advertisement_id="ad1",
                 created_at=now - timedelta(days=10),
                 status=LeadStatus.SUBMITTED)
            for i in range(40)
        ]

        # 28 of them were contacted
        call_attempts = [
            CallAttempt(id=f"c{i}", lead_id=f"l{i}",
                        attempted_at=now - timedelta(days=9),
                        outcome=CallOutcome.ANSWERED)
            for i in range(28)
        ]

        # 10 of the contacted leads were qualified (all past qualification window)
        quals = [
            QualificationOutcome(
                id=f"q{i}", lead_id=f"l{i}",
                resolved_at=now - timedelta(days=8),
                result=QualificationResult.QUALIFIED,
            )
            for i in range(10)
        ]
        # 18 disqualified
        quals += [
            QualificationOutcome(
                id=f"q{i}", lead_id=f"l{i}",
                resolved_at=now - timedelta(days=8),
                result=QualificationResult.DISQUALIFIED,
            )
            for i in range(10, 28)
        ]

        config = EstimatorConfig(
            contact_maturity_days=3.0,
            qualification_maturity_days=7.0,
        )
        rng = np.random.default_rng(42)
        snapshot = compute_estimates(
            advertisement=ad,
            leads=leads,
            call_attempts=call_attempts,
            qualification_outcomes=quals,
            observation_time=now,
            config=config,
            rng=rng,
        )

        # All 40 leads should be mature
        assert snapshot.n_mature_leads == 40
        # 28 contacted
        assert snapshot.n_contacts == 28
        # 28 contacts are mature (contacted 9 days ago, 9 > 7 qual window)
        assert snapshot.n_mature_contacts == 28
        # 10 qualified
        assert snapshot.k_qualified == 10

        # Reachability should be around 28/40 = 0.7 (with Bayesian regularization)
        assert 0.55 < snapshot.reachability_mean < 0.80

        # Qualification rate should be around 10/28 ≈ 0.36 (with Beta(1,4) prior pull)
        assert 0.20 < snapshot.qualification_mean < 0.50

        # CI should contain the mean
        assert snapshot.reachability_ci_low <= snapshot.reachability_mean <= snapshot.reachability_ci_high
        assert snapshot.qualification_ci_low <= snapshot.qualification_mean <= snapshot.qualification_ci_high

        # CPQL should be defined (we have enough data)
        assert snapshot.cpql_mean is not None
        assert snapshot.cpql_mean > 0

    def test_compute_estimates_and_decision_determinism(self):
        """Prove that the same inputs and seed give identical estimates and decisions across repeated calls."""
        from decision_engine import DecisionPolicy, evaluate
        from domain.enums import CallOutcome, QualificationResult, LeadStatus
        from domain.models import Advertisement, Lead, CallAttempt, QualificationOutcome

        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        ad = Advertisement(
            id="ad_det_1",
            ad_set_id="as1",
            creative_id="cr1",
            spend=500.0,
            impressions=10000,
            clicks=200,
        )
        leads = [
            Lead(id=f"l{i}", advertisement_id=ad.id,
                 created_at=now - timedelta(days=10),
                 status=LeadStatus.SUBMITTED)
            for i in range(25)
        ]
        call_attempts = [
            CallAttempt(id=f"c{i}", lead_id=f"l{i}",
                        attempted_at=now - timedelta(days=9),
                        outcome=CallOutcome.ANSWERED)
            for i in range(15)
        ]
        quals = [
            QualificationOutcome(
                id=f"q{i}", lead_id=f"l{i}",
                resolved_at=now - timedelta(days=8),
                result=QualificationResult.QUALIFIED if i < 5 else QualificationResult.DISQUALIFIED,
            )
            for i in range(15)
        ]
        policy = DecisionPolicy()

        # Run 1 without passing explicit rng (uses derived RNG from seed and ad.id)
        s1 = compute_estimates(ad, leads, call_attempts, quals, observation_time=now, seed=12345)
        d1 = evaluate(s1, ad_spend=ad.spend, policy=policy)

        # Run 2
        s2 = compute_estimates(ad, leads, call_attempts, quals, observation_time=now, seed=12345)
        d2 = evaluate(s2, ad_spend=ad.spend, policy=policy)

        # Exact equality check on all estimate fields
        assert s1.reachability_mean == s2.reachability_mean
        assert s1.reachability_ci_low == s2.reachability_ci_low
        assert s1.reachability_ci_high == s2.reachability_ci_high
        assert s1.qualification_mean == s2.qualification_mean
        assert s1.qualification_ci_low == s2.qualification_ci_low
        assert s1.qualification_ci_high == s2.qualification_ci_high
        assert s1.eql_mean == s2.eql_mean
        assert s1.eql_ci_low == s2.eql_ci_low
        assert s1.eql_ci_high == s2.eql_ci_high
        assert s1.cpql_mean == s2.cpql_mean
        assert s1.cpql_ci_low == s2.cpql_ci_low
        assert s1.cpql_ci_high == s2.cpql_ci_high
        assert s1.zero_eql_fraction == s2.zero_eql_fraction
        assert s1.cpql_unstable == s2.cpql_unstable

        # Exact equality check on decision
        assert d1.action == d2.action
        assert d1.confidence_level == d2.confidence_level
        assert d1.reason == d2.reason

