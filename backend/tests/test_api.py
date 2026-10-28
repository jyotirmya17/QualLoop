"""
Tests for FastAPI application endpoints.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.store import clear as clear_store
from audit.trail import clear_all as clear_audit
from domain.enums import DecisionAction, DecisionTier
from persistence.database import init_db, reset_engine, set_database_url


@pytest.fixture(autouse=True)
def isolated_api_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_api.db"
        set_database_url(f"sqlite:///{db_path}")
        init_db()
        clear_store()
        clear_audit()
        yield db_path
        reset_engine()
        set_database_url(None)


client = TestClient(app)


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


def test_simulation_explicit_evaluation_persists_decisions_and_audit_events():
    """
    1. A run can be evaluated and its decisions are persisted.
    2. Every persisted decision has its expected initial audit event.
    3. Audit events reference the correct decision IDs.
    4. The analysis response exposes the corresponding persisted IDs.
    """
    # 1. POST /simulations/run
    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "healthy_campaign", "seed": 42},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # Initial state: no decisions recorded in durable store
    init_decs = client.get(f"/decisions/?simulation_run_id={run_id}").json()
    assert len(init_decs) == 0

    # 2. Explicit evaluation via POST /simulations/{run_id}/evaluate
    eval_resp = client.post(f"/simulations/{run_id}/evaluate")
    assert eval_resp.status_code == 200
    eval_campaigns = eval_resp.json()
    assert len(eval_campaigns) > 0

    evaluated_decisions = []
    for camp in eval_campaigns:
        for ad_analysis in camp["ads"]:
            dec = ad_analysis["decision"]
            assert dec["id"]
            assert dec["simulation_run_id"] == run_id
            assert dec["is_persisted"] is True
            evaluated_decisions.append(dec)

    assert len(evaluated_decisions) > 0

    # 3. Verify GET /decisions/ returns the matching durable records
    db_decs = client.get(f"/decisions/?simulation_run_id={run_id}").json()
    assert len(db_decs) == len(evaluated_decisions)
    eval_ids = {d["id"] for d in evaluated_decisions}
    db_ids = {d["id"] for d in db_decs}
    assert eval_ids == db_ids

    # 4. Verify each persisted decision has an initial audit event referencing its ID
    for dec_id in eval_ids:
        audit_resp = client.get(f"/audit/?decision_id={dec_id}")
        assert audit_resp.status_code == 200
        events = audit_resp.json()
        assert len(events) == 1
        assert events[0]["decision_id"] == dec_id
        assert events[0]["event_type"] == "decision_created"

    # 5. Verify GET /ads/run/{run_id} exposes the persisted decision IDs
    analysis_resp = client.get(f"/ads/run/{run_id}")
    assert analysis_resp.status_code == 200
    retrieved_campaigns = analysis_resp.json()
    retrieved_ids = {
        ad["decision"]["id"]
        for camp in retrieved_campaigns
        for ad in camp["ads"]
    }
    assert retrieved_ids == eval_ids


def test_repeated_get_does_not_write_new_decisions():
    """6. Repeated GET requests do not write new decisions."""
    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "mixed_portfolio", "seed": 99},
    )
    run_id = run_resp.json()["id"]

    # Before GET requests: store is empty
    assert len(client.get("/decisions/").json()) == 0

    # Issue multiple GET requests
    for _ in range(3):
        resp = client.get(f"/ads/run/{run_id}")
        assert resp.status_code == 200
        for camp in resp.json():
            for ad in camp["ads"]:
                assert ad["decision"]["is_persisted"] is False

    # Store must remain empty: pure read operation
    assert len(client.get("/decisions/").json()) == 0
    assert len(client.get("/audit/").json()) == 0


def test_repeating_evaluation_is_idempotent():
    """5. Repeating evaluation does not increase the number of decisions or creation events."""
    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "healthy_campaign", "seed": 77},
    )
    run_id = run_resp.json()["id"]

    # First evaluation
    eval_resp_1 = client.post(f"/simulations/{run_id}/evaluate")
    assert eval_resp_1.status_code == 200
    campaigns_1 = eval_resp_1.json()
    dec_ids_1 = [
        ad["decision"]["id"] for camp in campaigns_1 for ad in camp["ads"]
    ]

    total_decs_1 = len(client.get(f"/decisions/?simulation_run_id={run_id}").json())
    total_audits_1 = len(client.get("/audit/").json())
    assert total_decs_1 > 0

    # Second evaluation (same route)
    eval_resp_2 = client.post(f"/simulations/{run_id}/evaluate")
    assert eval_resp_2.status_code == 200
    campaigns_2 = eval_resp_2.json()
    dec_ids_2 = [
        ad["decision"]["id"] for camp in campaigns_2 for ad in camp["ads"]
    ]

    # Third evaluation via ads router alias
    eval_resp_3 = client.post(f"/ads/run/{run_id}/evaluate")
    assert eval_resp_3.status_code == 200
    campaigns_3 = eval_resp_3.json()
    dec_ids_3 = [
        ad["decision"]["id"] for camp in campaigns_3 for ad in camp["ads"]
    ]

    # IDs must be preserved identically
    assert dec_ids_1 == dec_ids_2 == dec_ids_3

    # Total counts must not increase
    total_decs_after = len(client.get(f"/decisions/?simulation_run_id={run_id}").json())
    total_audits_after = len(client.get("/audit/").json())
    assert total_decs_after == total_decs_1
    assert total_audits_after == total_audits_1


def test_persistence_failure_is_surfaced_rather_than_reported_as_success(monkeypatch):
    """7. A persistence failure is surfaced rather than reported as success."""
    from unittest.mock import MagicMock

    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "healthy_campaign", "seed": 55},
    )
    run_id = run_resp.json()["id"]

    def faulty_record_decisions(decisions):
        raise RuntimeError("Simulated disk I/O write failure")

    monkeypatch.setattr("api.evaluation.record_decisions", faulty_record_decisions)

    # Calling evaluate must fail and raise the error, not report success
    with pytest.raises(RuntimeError, match="Simulated disk I/O write failure"):
        client.post(f"/simulations/{run_id}/evaluate")

    # Ledger remains empty
    assert len(client.get(f"/decisions/?simulation_run_id={run_id}").json()) == 0


def test_decisions_and_audit_survive_engine_reset_in_isolated_db():
    """8. Existing decisions and audit events survive database/engine reset."""
    run_resp = client.post(
        "/simulations/run",
        json={"scenario_name": "healthy_campaign", "seed": 33},
    )
    run_id = run_resp.json()["id"]
    eval_resp = client.post(f"/simulations/{run_id}/evaluate")
    assert eval_resp.status_code == 200
    initial_ids = {
        ad["decision"]["id"]
        for camp in eval_resp.json()
        for ad in camp["ads"]
    }

    # Reset engine (closing connections and connection pools)
    reset_engine()

    # Query again through fresh connections
    persisted_decs = client.get(f"/decisions/?simulation_run_id={run_id}").json()
    assert len(persisted_decs) == len(initial_ids)
    assert {d["id"] for d in persisted_decs} == initial_ids

    # Analysis endpoint reloads persisted decision IDs
    analysis_resp = client.get(f"/ads/run/{run_id}")
    assert analysis_resp.status_code == 200
    reloaded_ids = {
        ad["decision"]["id"]
        for camp in analysis_resp.json()
        for ad in camp["ads"]
    }
    assert reloaded_ids == initial_ids

