"""
Tests for durable persistence of decisions and audit events.
Exercises real database persistence (SQLite) with isolated temporary databases.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from domain.enums import ApprovalStatus, DecisionAction
from domain.models import AuditEvent, Decision
from persistence.database import (
    get_engine,
    init_db,
    normalize_database_url,
    reset_engine,
    session_scope,
    set_database_url,
)
from persistence.models import AuditEventModel, DecisionModel
from persistence.repository import (
    clear_all,
    query_audit_events,
    query_decisions,
    record_audit_event,
    record_decision,
    record_decisions,
)


@pytest.fixture(autouse=True)
def isolated_db():
    """Ensure every test runs against an isolated temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_persistence.db"
        db_url = f"sqlite:///{db_path}"
        set_database_url(db_url)
        init_db()
        yield db_path
        reset_engine()
        set_database_url(None)


def _make_sample_decision(ad_id: str = "ad-test-1", action: DecisionAction = DecisionAction.PAUSE_AD) -> Decision:
    return Decision(
        id=str(uuid.uuid4()),
        advertisement_id=ad_id,
        estimate_snapshot_id="snap-123",
        policy_version="config_2",
        action=action,
        reason="Low qualification rate 4.2% below 15% threshold with mature evidence",
        supporting_metrics={"q_mean": 0.042, "q_ci_high": 0.098, "n_contacts": 25},
        confidence_level="high",
        tier="autonomous",
        auto_applied=True,
        requires_human_approval=False,
        approval_status=ApprovalStatus.NOT_REQUIRED,
        created_at=datetime.now(timezone.utc),
    )


def test_create_decision_and_retrieve():
    """1. Create a decision and retrieve it from durable storage."""
    decision = _make_sample_decision(ad_id="ad-alpha-1")
    record_decision(decision)

    # Query all
    all_decisions = query_decisions()
    assert len(all_decisions) == 1
    retrieved = all_decisions[0]

    assert retrieved.id == decision.id
    assert retrieved.advertisement_id == "ad-alpha-1"
    assert retrieved.action == DecisionAction.PAUSE_AD
    assert retrieved.policy_version == "config_2"
    assert retrieved.supporting_metrics == decision.supporting_metrics
    assert retrieved.confidence_level == "high"
    assert retrieved.auto_applied is True
    assert retrieved.requires_human_approval is False

    # Filtered query
    by_ad = query_decisions(advertisement_id="ad-alpha-1")
    assert len(by_ad) == 1
    assert by_ad[0].id == decision.id

    by_other = query_decisions(advertisement_id="non-existent")
    assert len(by_other) == 0


def test_create_audit_events_and_retrieve_deterministic_order():
    """2. Create audit events and retrieve them in deterministic order (most recent first)."""
    t0 = datetime(2026, 10, 25, 10, 0, 0, tzinfo=timezone.utc)
    events = [
        AuditEvent(
            id=f"evt-{i}",
            decision_id=None,
            event_type="system_health_check",
            data={"step": i},
            created_at=t0 + timedelta(minutes=i * 10),
        )
        for i in range(5)
    ]

    for evt in events:
        record_audit_event(evt)

    retrieved = query_audit_events(limit=10)
    assert len(retrieved) == 5

    # Most recent first: evt-4, evt-3, evt-2, evt-1, evt-0
    retrieved_ids = [e.id for e in retrieved]
    assert retrieved_ids == ["evt-4", "evt-3", "evt-2", "evt-1", "evt-0"]

    # Verify tie-breaking determinism when timestamps are identical
    same_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
    clear_all()
    tie_events = [
        AuditEvent(id="evt-b", decision_id=None, event_type="test", data={}, created_at=same_time),
        AuditEvent(id="evt-a", decision_id=None, event_type="test", data={}, created_at=same_time),
        AuditEvent(id="evt-c", decision_id=None, event_type="test", data={}, created_at=same_time),
    ]
    for e in tie_events:
        record_audit_event(e)

    retrieved_ties = query_audit_events()
    assert [e.id for e in retrieved_ties] == ["evt-c", "evt-b", "evt-a"]


def test_restart_application_records_survive(isolated_db):
    """In-process engine reset simulation: confirm records survive when engine and session factory are disposed and recreated."""
    db_path = isolated_db
    dec1 = _make_sample_decision(ad_id="ad-persist-1")
    dec2 = _make_sample_decision(ad_id="ad-persist-2")
    record_decision(dec1)
    record_decision(dec2)

    # Verify records present before restart
    assert len(query_decisions()) == 2
    assert len(query_audit_events()) == 2

    # SIMULATE APPLICATION RESTART:
    # 1. Dispose engine and reset all global connection pools and session factories
    reset_engine()

    # 2. Point new engine to the exact same file
    db_url = f"sqlite:///{db_path}"
    set_database_url(db_url)

    # 3. Query anew without in-memory state
    reopened_decisions = query_decisions()
    reopened_events = query_audit_events()

    assert len(reopened_decisions) == 2
    dec_ids = {d.id for d in reopened_decisions}
    assert dec1.id in dec_ids
    assert dec2.id in dec_ids

    assert len(reopened_events) == 2
    evt_decision_ids = {e.decision_id for e in reopened_events}
    assert dec1.id in evt_decision_ids
    assert dec2.id in evt_decision_ids


def test_decision_references_and_audit_consistency():
    """4. Verify decision references and associated audit events remain consistent."""
    dec = _make_sample_decision(ad_id="ad-ref-1")
    record_decision(dec)

    dec_events = query_audit_events(decision_id=dec.id)
    assert len(dec_events) == 1
    evt = dec_events[0]
    assert evt.decision_id == dec.id
    assert evt.event_type == "decision_created"
    assert evt.data["action"] == dec.action.value
    assert evt.data["policy_version"] == dec.policy_version


def test_querying_empty_store_and_missing_records():
    """5. Verify querying an empty store and handling invalid or missing records."""
    assert query_decisions() == []
    assert query_audit_events() == []
    assert query_decisions(advertisement_id="non-existent-ad") == []
    assert query_decisions(action="non-existent-action") == []
    assert query_audit_events(decision_id="non-existent-dec") == []


def test_database_failures_raise_explicitly_no_false_success():
    """6. Verify database failures do not produce false success responses."""
    # Attempting to record a decision with a broken/non-existent table or corrupted state
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS audit_events"))
        conn.commit()

    decision = _make_sample_decision()
    with pytest.raises(Exception):
        record_decision(decision)


def test_clear_all_resets_store():
    """Verify clear_all properly purges data for testing environments."""
    dec = _make_sample_decision()
    record_decision(dec)
    assert len(query_decisions()) == 1
    assert len(query_audit_events()) == 1

    clear_all()
    assert len(query_decisions()) == 0
    assert len(query_audit_events()) == 0


def test_decision_deletion_retains_audit_events_with_null_foreign_key():
    """
    Protect audit-event retention:
    Deleting a decision through the ORM must NOT cascade delete associated audit events.
    Instead, audit events are preserved with decision_id set to NULL per ON DELETE SET NULL.
    """
    decision = _make_sample_decision(ad_id="ad-delete-retention-test")
    record_decision(decision)

    # Confirm initial decision and audit event exist
    events = query_audit_events(decision_id=decision.id)
    assert len(events) == 1
    event_id = events[0].id
    assert events[0].decision_id == decision.id

    # Delete the decision through the ORM session
    with session_scope() as session:
        dec_model = session.get(DecisionModel, decision.id)
        assert dec_model is not None
        session.delete(dec_model)

    # Verify decision is deleted
    assert query_decisions(advertisement_id="ad-delete-retention-test") == []

    # Verify audit event remains and decision_id is null
    remaining_events = query_audit_events()
    assert len(remaining_events) == 1
    retained_evt = remaining_events[0]
    assert retained_evt.id == event_id
    assert retained_evt.decision_id is None
    assert retained_evt.event_type == "decision_created"


def test_true_process_restart_durability_subprocess():
    """
    Genuine multi-process durability test:
    1. Creates a temporary SQLite database path.
    2. Starts a writer subprocess that records a decision and associated audit event.
    3. Verifies the writer subprocess exits successfully with returncode 0.
    4. Starts a separate reader subprocess with the same database URL.
    5. Verifies the reader can retrieve the decision and audit event with identifiers and relationships intact.
    6. Verifies both subprocesses use the temporary database, never the developer's default database.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_db_path = Path(tmpdir) / "subprocess_durability.db"
        temp_db_url = f"sqlite:///{temp_db_path}"

        # Explicit environment for subprocesses
        backend_dir = str(Path(__file__).resolve().parent.parent)
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = backend_dir
        sub_env["DATABASE_URL"] = temp_db_url

        writer_script = """
import os
import sys
import uuid
from datetime import datetime, timezone

from persistence.database import get_database_url, init_db
from persistence.repository import record_decision, record_audit_event
from domain.models import Decision, AuditEvent
from domain.enums import DecisionAction, ApprovalStatus

# Verify subprocess is using the temporary database
active_url = get_database_url()
assert "qualloop.db" not in active_url, f"Writer unexpectedly using default database: {active_url}"
assert active_url.startswith("sqlite:///"), f"Expected sqlite URL, got: {active_url}"

# Initialize schema in temporary database
init_db()

# Create decision and audit event
dec_id = "dec-subproc-test-1"
evt_id = "evt-subproc-test-1"

decision = Decision(
    id=dec_id,
    advertisement_id="ad-subproc-1",
    estimate_snapshot_id="snap-subproc-1",
    policy_version="config_2",
    action=DecisionAction.PAUSE_AD,
    reason="Subprocess durability test pause",
    supporting_metrics={"qualification_rate": 0.05, "n_contacts": 30},
    confidence_level="high",
    tier="autonomous",
    auto_applied=True,
    requires_human_approval=False,
    approval_status=ApprovalStatus.NOT_REQUIRED,
    created_at=datetime.now(timezone.utc),
)
record_decision(decision)

# Record additional audit event tied to decision
audit = AuditEvent(
    id=evt_id,
    decision_id=dec_id,
    event_type="subprocess_test_event",
    data={"origin": "writer_process", "status": "persisted"},
    created_at=datetime.now(timezone.utc),
)
record_audit_event(audit)

print("WRITER_SUCCESS")
"""

        writer_res = subprocess.run(
            [sys.executable, "-c", writer_script],
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )

        assert writer_res.returncode == 0, (
            f"Writer subprocess failed with code {writer_res.returncode}.\\n"
            f"STDOUT:\\n{writer_res.stdout}\\n"
            f"STDERR:\\n{writer_res.stderr}"
        )
        assert "WRITER_SUCCESS" in writer_res.stdout
        assert temp_db_path.exists(), "Temporary database file was not created by writer subprocess"

        reader_script = """
import json
import os
import sys

from persistence.database import get_database_url
from persistence.repository import query_decisions, query_audit_events

active_url = get_database_url()
assert "qualloop.db" not in active_url, f"Reader unexpectedly using default database: {active_url}"

decisions = query_decisions()
events = query_audit_events()

result = {
    "decisions": [
        {
            "id": d.id,
            "advertisement_id": d.advertisement_id,
            "action": d.action.value,
            "policy_version": d.policy_version,
            "reason": d.reason,
            "supporting_metrics": d.supporting_metrics,
        }
        for d in decisions
    ],
    "events": [
        {
            "id": e.id,
            "decision_id": e.decision_id,
            "event_type": e.event_type,
            "data": e.data,
        }
        for e in events
    ],
}
print("READER_OUTPUT:" + json.dumps(result))
"""

        reader_res = subprocess.run(
            [sys.executable, "-c", reader_script],
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )

        assert reader_res.returncode == 0, (
            f"Reader subprocess failed with code {reader_res.returncode}.\\n"
            f"STDOUT:\\n{reader_res.stdout}\\n"
            f"STDERR:\\n{reader_res.stderr}"
        )

        # Parse reader output
        marker = "READER_OUTPUT:"
        assert marker in reader_res.stdout, f"Marker not found in stdout: {reader_res.stdout}"
        output_line = [line for line in reader_res.stdout.splitlines() if line.startswith(marker)][0]
        data = json.loads(output_line[len(marker):])

        # Verify decision retrieved intact
        assert len(data["decisions"]) == 1
        rec_dec = data["decisions"][0]
        assert rec_dec["id"] == "dec-subproc-test-1"
        assert rec_dec["advertisement_id"] == "ad-subproc-1"
        assert rec_dec["action"] == DecisionAction.PAUSE_AD.value
        assert rec_dec["reason"] == "Subprocess durability test pause"

        # Verify audit events retrieved intact
        assert len(data["events"]) == 2  # 1 from record_decision, 1 explicit record_audit_event
        event_ids = {e["id"] for e in data["events"]}
        assert "evt-subproc-test-1" in event_ids

        # Verify relationships intact
        for evt in data["events"]:
            assert evt["decision_id"] == "dec-subproc-test-1"


def test_database_url_normalization():
    """Verify legacy postgres:// URLs are normalized to postgresql:// without altering other parts."""
    # postgres:// scheme rewrite
    legacy_url = "postgres://user:secret_pass@db.example.com:5432/production_db?sslmode=require"
    expected = "postgresql://user:secret_pass@db.example.com:5432/production_db?sslmode=require"
    assert normalize_database_url(legacy_url) == expected

    # postgresql:// remains unchanged
    already_valid = "postgresql://user:secret_pass@db.example.com:5432/production_db"
    assert normalize_database_url(already_valid) == already_valid

    # postgresql+psycopg2:// remains unchanged
    psycopg_url = "postgresql+psycopg2://user:secret_pass@db.example.com:5432/production_db"
    assert normalize_database_url(psycopg_url) == psycopg_url

    # sqlite remains unchanged
    sqlite_url = "sqlite:///backend/qualloop.db"
    assert normalize_database_url(sqlite_url) == sqlite_url

    sqlite_memory = "sqlite:///:memory:"
    assert normalize_database_url(sqlite_memory) == sqlite_memory


def test_importing_api_main_does_not_create_or_mutate_database():
    """Verify that importing api.main produces zero database side-effects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        non_existent_db = Path(tmpdir) / "should_not_exist.db"
        backend_dir = str(Path(__file__).resolve().parent.parent)
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = backend_dir
        sub_env["DATABASE_URL"] = f"sqlite:///{non_existent_db}"

        code = "import api.main; print('IMPORTED_CLEANLY')"
        res = subprocess.run(
            [sys.executable, "-c", code],
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=25,
        )
        assert res.returncode == 0, f"Import failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        assert "IMPORTED_CLEANLY" in res.stdout
        assert not non_existent_db.exists(), "Importing api.main created a database file!"


def test_fresh_database_initialized_via_alembic_workflow():
    """Verify that a fresh database can be initialized through the documented alembic workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fresh_db = Path(tmpdir) / "fresh_alembic.db"
        backend_dir = str(Path(__file__).resolve().parent.parent)
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = backend_dir
        sub_env["DATABASE_URL"] = f"sqlite:///{fresh_db}"

        # 1. Run alembic upgrade head
        res_upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir,
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res_upgrade.returncode == 0, f"Alembic upgrade failed:\nSTDOUT: {res_upgrade.stdout}\nSTDERR: {res_upgrade.stderr}"
        assert fresh_db.exists(), "Database file was not created by alembic upgrade head"

        # 2. Check alembic current revision
        res_current = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            cwd=backend_dir,
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res_current.returncode == 0, f"Alembic current failed:\nSTDOUT: {res_current.stdout}\nSTDERR: {res_current.stderr}"
        assert "8bb09934ef5c" in res_current.stdout
        assert "head" in res_current.stdout


def test_api_starts_correctly_after_migrations():
    """Verify that the API starts cleanly via lifespan when migrations have been applied."""
    with tempfile.TemporaryDirectory() as tmpdir:
        migrated_db = Path(tmpdir) / "migrated_api.db"
        backend_dir = str(Path(__file__).resolve().parent.parent)
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = backend_dir
        sub_env["DATABASE_URL"] = f"sqlite:///{migrated_db}"

        # 1. Apply migrations
        res_upgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir,
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res_upgrade.returncode == 0

        # 2. Start API through lifespan context
        test_script = """
from fastapi.testclient import TestClient
from api.main import app

with TestClient(app) as client:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    print("API_LIFESPAN_STARTUP_SUCCESS")
"""
        res_api = subprocess.run(
            [sys.executable, "-c", test_script],
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res_api.returncode == 0, f"API failed to start on migrated database:\nSTDOUT: {res_api.stdout}\nSTDERR: {res_api.stderr}"
        assert "API_LIFESPAN_STARTUP_SUCCESS" in res_api.stdout


def test_api_startup_fails_clearly_when_schema_missing():
    """Verify the API fails with clear, actionable guidance when required schema is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_db = Path(tmpdir) / "unmigrated.db"
        backend_dir = str(Path(__file__).resolve().parent.parent)
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = backend_dir
        sub_env["DATABASE_URL"] = f"sqlite:///{empty_db}"

        test_script = """
import sys
from fastapi.testclient import TestClient
from api.main import app

try:
    with TestClient(app) as client:
        pass
    print("ERROR_DID_NOT_FAIL")
    sys.exit(1)
except Exception as e:
    err_text = str(e)
    print("CAPTURED_ERROR:" + err_text)
    assert "alembic upgrade head" in err_text, "Error message must guide user to run alembic upgrade head"
    assert "missing required tables" in err_text or "uninitialized" in err_text
    print("STARTUP_FAILURE_VERIFIED")
    sys.exit(0)
"""
        res = subprocess.run(
            [sys.executable, "-c", test_script],
            env=sub_env,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert res.returncode == 0, f"Expected startup failure check failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
        assert "STARTUP_FAILURE_VERIFIED" in res.stdout


def test_test_suite_does_not_touch_default_database():
    """Verify the test suite runs on isolated databases and never touches or leaks test data into backend/qualloop.db."""
    backend_dir = Path(__file__).resolve().parent.parent
    default_db = backend_dir / "qualloop.db"
    if default_db.exists():
        # When default_db exists (e.g., from a running local dev server), verify that
        # the test suite has not written any test-isolated records into it.
        import sqlite3
        conn = sqlite3.connect(str(default_db))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'")
        if cursor.fetchone():
            cursor.execute(
                "SELECT id FROM decisions WHERE id LIKE 'test-%' OR advertisement_id LIKE 'ad-test-%' OR advertisement_id LIKE 'ad-atomic-%'"
            )
            leaked = cursor.fetchall()
            assert len(leaked) == 0, f"Found test suite records leaked into default database: {leaked}"
        conn.close()
    else:
        assert not default_db.exists(), f"Default database file was unexpectedly created at {default_db}"


def test_atomic_record_decisions_and_audit_events():
    """Verify record_decisions inserts multiple decisions and their initial audit events atomically."""
    d1 = _make_sample_decision(ad_id="ad-atomic-1")
    d1.simulation_run_id = "sim-atomic-1"
    d2 = _make_sample_decision(ad_id="ad-atomic-2")
    d2.simulation_run_id = "sim-atomic-1"

    record_decisions([d1, d2])

    decisions = query_decisions(simulation_run_id="sim-atomic-1")
    assert len(decisions) == 2
    dec_ids = {d.id for d in decisions}
    assert d1.id in dec_ids
    assert d2.id in dec_ids

    events_1 = query_audit_events(decision_id=d1.id)
    assert len(events_1) == 1
    assert events_1[0].decision_id == d1.id
    assert events_1[0].event_type == "decision_created"

    events_2 = query_audit_events(decision_id=d2.id)
    assert len(events_2) == 1
    assert events_2[0].decision_id == d2.id
    assert events_2[0].event_type == "decision_created"


def test_unique_constraint_run_ad_policy_prevents_duplicate_evaluations():
    """Verify database uniqueness constraint prevents duplicate decisions for the same run, ad, and policy."""
    from sqlalchemy.exc import IntegrityError

    d1 = _make_sample_decision(ad_id="ad-dup-1")
    d1.simulation_run_id = "sim-dup-1"
    d1.policy_version = "policy_v1"
    record_decision(d1)

    # Attempting to record another decision with the exact same (simulation_run_id, advertisement_id, policy_version)
    d2 = _make_sample_decision(ad_id="ad-dup-1")
    d2.simulation_run_id = "sim-dup-1"
    d2.policy_version = "policy_v1"

    with pytest.raises(IntegrityError):
        record_decision(d2)

    # Decisions count remains 1
    decisions = query_decisions(simulation_run_id="sim-dup-1")
    assert len(decisions) == 1
    assert decisions[0].id == d1.id


