"""
Audit trail — durable store for decision records and audit events.

Delegates to the persistence layer (SQLAlchemy + SQLite/PostgreSQL)
so decisions and audit events survive process restarts while maintaining
identical interfaces for existing callers and tests.
"""

from __future__ import annotations

from typing import Optional

from domain.models import AuditEvent, Decision
from persistence.repository import (
    clear_all as _clear_all,
    query_audit_events as _query_audit_events,
    query_decisions as _query_decisions,
    record_decision as _record_decision,
    record_decisions as _record_decisions,
)


def record_decision(decision: Decision) -> None:
    """Append a decision to the audit trail. Immutable — no updates allowed."""
    _record_decision(decision)


def record_decisions(decisions: list[Decision]) -> None:
    """Append multiple decisions to the audit trail atomically."""
    _record_decisions(decisions)


def query_decisions(
    advertisement_id: Optional[str] = None,
    action: Optional[str] = None,
    simulation_run_id: Optional[str] = None,
    limit: int = 100,
) -> list[Decision]:
    """Query decisions from the audit trail with optional filters."""
    return _query_decisions(
        advertisement_id=advertisement_id,
        action=action,
        simulation_run_id=simulation_run_id,
        limit=limit,
    )


def query_audit_events(
    decision_id: Optional[str] = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """Query raw audit events."""
    return _query_audit_events(decision_id=decision_id, limit=limit)


def clear_all() -> None:
    """Clear store. Only for testing."""
    _clear_all()
