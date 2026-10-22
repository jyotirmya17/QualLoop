"""
Tests for the synthetic data simulator.

Tests verify:
- Same seed → reproducible output
- Different seeds → different output
- All generated relationships are valid
- Ground truth is correctly isolated (not leaked to production view)
- Delayed outcomes follow configured rules
- All scenario presets can be run
"""

import pytest

from simulator import SCENARIO_REGISTRY, get_scenario, run_simulation
from simulator.engine import SimulationResult
from simulator.scenarios import ScenarioConfig, healthy_campaign, small_sample_trap


class TestReproducibility:
    def test_same_seed_produces_identical_output(self):
        config = healthy_campaign(seed=42)
        result1 = run_simulation(config)
        result2 = run_simulation(config)

        assert len(result1.leads) == len(result2.leads)
        lead_ids_1 = {l.id for l in result1.leads}
        lead_ids_2 = {l.id for l in result2.leads}
        assert lead_ids_1 == lead_ids_2

    def test_same_seed_produces_identical_call_attempts(self):
        config = healthy_campaign(seed=99)
        r1 = run_simulation(config)
        r2 = run_simulation(config)
        ca_ids_1 = {ca.id for ca in r1.call_attempts}
        ca_ids_2 = {ca.id for ca in r2.call_attempts}
        assert ca_ids_1 == ca_ids_2

    def test_different_seeds_produce_different_output(self):
        config_a = healthy_campaign(seed=1)
        config_b = healthy_campaign(seed=2)
        result_a = run_simulation(config_a)
        result_b = run_simulation(config_b)
        # Different seeds — at least the lead IDs should differ
        ids_a = {l.id for l in result_a.leads}
        ids_b = {l.id for l in result_b.leads}
        assert ids_a != ids_b, "Different seeds should produce different lead IDs"


class TestDataIntegrity:
    def test_leads_reference_valid_advertisements(self):
        config = healthy_campaign(seed=10)
        result = run_simulation(config)
        ad_ids = {ad.id for ad in result.advertisements}
        for lead in result.leads:
            assert lead.advertisement_id in ad_ids, (
                f"Lead {lead.id} references unknown ad {lead.advertisement_id}"
            )

    def test_call_attempts_reference_valid_leads(self):
        config = healthy_campaign(seed=11)
        result = run_simulation(config)
        lead_ids = {l.id for l in result.leads}
        for ca in result.call_attempts:
            assert ca.lead_id in lead_ids, (
                f"CallAttempt {ca.id} references unknown lead {ca.lead_id}"
            )

    def test_qualification_outcomes_reference_valid_leads(self):
        config = healthy_campaign(seed=12)
        result = run_simulation(config)
        lead_ids = {l.id for l in result.leads}
        for qo in result.qualification_outcomes:
            assert qo.lead_id in lead_ids, (
                f"QualificationOutcome {qo.id} references unknown lead {qo.lead_id}"
            )

    def test_ad_sets_reference_valid_campaigns(self):
        config = healthy_campaign(seed=13)
        result = run_simulation(config)
        campaign_ids = {c.id for c in result.campaigns}
        for ad_set in result.ad_sets:
            assert ad_set.campaign_id in campaign_ids

    def test_ads_reference_valid_ad_sets(self):
        config = healthy_campaign(seed=14)
        result = run_simulation(config)
        ad_set_ids = {ads.id for ads in result.ad_sets}
        for ad in result.advertisements:
            assert ad.ad_set_id in ad_set_ids

    def test_leads_have_valid_created_at(self):
        config = healthy_campaign(seed=15)
        result = run_simulation(config)
        for lead in result.leads:
            assert lead.created_at is not None

    def test_spend_is_non_negative(self):
        config = healthy_campaign(seed=16)
        result = run_simulation(config)
        for ad in result.advertisements:
            assert ad.spend >= 0


class TestGroundTruthIsolation:
    def test_production_view_has_empty_ground_truth(self):
        config = healthy_campaign(seed=20)
        result = run_simulation(config)

        # Full result has ground truth
        assert len(result.ground_truth) > 0

        # Production view strips it
        prod = result.production_view()
        assert len(prod.ground_truth) == 0

    def test_production_view_preserves_leads(self):
        config = healthy_campaign(seed=21)
        result = run_simulation(config)
        prod = result.production_view()
        assert len(prod.leads) == len(result.leads)

    def test_production_view_preserves_ads(self):
        config = healthy_campaign(seed=22)
        result = run_simulation(config)
        prod = result.production_view()
        assert len(prod.advertisements) == len(result.advertisements)

    def test_ground_truth_has_true_reachability_for_each_ad(self):
        config = healthy_campaign(seed=23)
        result = run_simulation(config)
        ad_ids = {ad.id for ad in result.advertisements}
        gt_ad_ids = {gt.advertisement_id for gt in result.ground_truth}
        assert ad_ids == gt_ad_ids


class TestScenarioPresets:
    @pytest.mark.parametrize("scenario_name", list(SCENARIO_REGISTRY.keys()))
    def test_all_scenarios_run_successfully(self, scenario_name):
        config = get_scenario(scenario_name, seed=42)
        result = run_simulation(config)
        assert result.run.scenario_name == scenario_name
        assert len(result.advertisements) >= 1
        assert len(result.leads) >= 0  # some scenarios may have low lead rates

    def test_small_sample_trap_produces_few_leads(self):
        config = small_sample_trap(seed=42)
        result = run_simulation(config)
        # With 1.5 leads/day over 14 days, expect roughly ~21 leads (±variance)
        assert result.run.n_leads < 60, "Small sample scenario should have modest lead count"

    def test_unknown_scenario_raises(self):
        with pytest.raises(ValueError, match="Unknown scenario"):
            get_scenario("nonexistent_scenario", seed=1)


class TestQualificationOutcomeTiming:
    def test_qualification_outcomes_are_after_contact(self):
        """Qualification resolution must happen after the contact call."""
        config = healthy_campaign(seed=30)
        result = run_simulation(config)

        # Index call attempts by lead_id
        first_contact = {}
        for ca in result.call_attempts:
            from domain.enums import CallOutcome
            if ca.outcome == CallOutcome.ANSWERED:
                if ca.lead_id not in first_contact:
                    first_contact[ca.lead_id] = ca.attempted_at

        for qo in result.qualification_outcomes:
            contact_time = first_contact.get(qo.lead_id)
            if contact_time is not None:
                assert qo.resolved_at >= contact_time, (
                    f"Qualification at {qo.resolved_at} is before contact at {contact_time}"
                )

    def test_run_metadata_is_correct(self):
        config = healthy_campaign(seed=40)
        result = run_simulation(config)
        assert result.run.n_leads == len(result.leads)
        assert result.run.n_ads == len(result.advertisements)
        assert result.run.completed_at is not None
        assert result.run.completed_at > result.run.started_at
