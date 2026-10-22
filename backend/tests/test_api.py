"""
Tests for FastAPI application endpoints.
"""

from fastapi.testclient import TestClient
from api.main import app
from api.store import clear as clear_store
from audit.trail import clear_all as clear_audit
from domain.enums import DecisionAction, DecisionTier

client = TestClient(app)


def setup_function():
    clear_store()
    clear_audit()


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["simulated_data_only"] is True
    assert "SIMULATED DATA" in data["warning"]


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["simulated_data_only"] is True


def test_list_scenarios():
    response = client.get("/simulations/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert "healthy_campaign" in data["scenarios"]
    assert "small_sample_trap" in data["scenarios"]
    assert "mixed_portfolio" in data["scenarios"]


def test_run_simulation_and_get():
    # 1. Run a simulation
    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "healthy_campaign", "seed": 42},
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    assert "id" in run_data
    assert run_data["scenario_name"] == "healthy_campaign"
    assert run_data["n_ads"] > 0
    assert run_data["n_leads"] > 0

    run_id = run_data["id"]

    # 2. Get simulation by id
    get_resp = client.get(f"/simulations/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == run_id

    # 3. List simulations
    list_resp = client.get("/simulations/")
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert len(runs) >= 1
    assert runs[0]["id"] == run_id


def test_run_simulation_unknown_scenario():
    response = client.post(
        "/simulations/run",
        json={"scenario_name": "non_existent_scenario", "seed": 42},
    )
    assert response.status_code == 422


def test_get_run_analysis():
    # Run a simulation first
    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "mixed_portfolio", "seed": 123},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # Get campaign and ad analysis
    analysis_resp = client.get(f"/ads/run/{run_id}")
    assert analysis_resp.status_code == 200
    campaigns = analysis_resp.json()
    assert len(campaigns) > 0

    for campaign in campaigns:
        assert campaign["campaign_name"]
        assert len(campaign["ads"]) > 0
        for ad_analysis in campaign["ads"]:
            assert "advertisement" in ad_analysis
            assert "estimate" in ad_analysis
            assert "decision" in ad_analysis
            assert ad_analysis["simulated_data_warning"] == "SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT"

            est = ad_analysis["estimate"]
            dec = ad_analysis["decision"]
            assert 0.0 <= est["reachability_mean"] <= 1.0
            assert 0.0 <= est["qualification_mean"] <= 1.0
            assert est["reachability_ci_low"] <= est["reachability_ci_high"]
            assert dec["action"] in [a.value for a in DecisionAction]
            assert dec["tier"] in [t.value for t in DecisionTier]
            assert isinstance(dec["auto_applied"], bool)


def test_get_run_analysis_not_found():
    response = client.get("/ads/run/unknown-run-id-999")
    assert response.status_code == 404


def test_benchmark_endpoints():
    # 1. GET /benchmark/latest
    resp = client.get("/benchmark/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert "aggregate_metrics" in data
    assert "qualloop" in data["aggregate_metrics"]
    assert "baseline" in data["aggregate_metrics"]


def test_decisions_and_audit_endpoints():
    dec_resp = client.get("/decisions/")
    assert dec_resp.status_code == 200
    assert isinstance(dec_resp.json(), list)

    audit_resp = client.get("/audit/")
    assert audit_resp.status_code == 200
    assert isinstance(audit_resp.json(), list)

