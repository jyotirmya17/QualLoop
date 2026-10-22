"""
Audit trail — in-memory store for decision records.

In v1, decisions are kept in an in-memory list. The persistence layer
(SQLAlchemy + PostgreSQL) will replace this when the API is running with
a live database. The in-memory implementation allows the core modules and
tests to run without a database dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.models import AuditEvent, Decision

# In-memory store (replaced by DB in production)
_decisions: list[Decision] = []
_audit_events: list[AuditEvent] = []


def record_decision(decision: Decision) -> None:
    """Append a decision to the audit trail. Immutable — no updates allowed."""
    _decisions.append(decision)
    _audit_events.append(
        AuditEvent(
            decision_id=decision.id,
            event_type="decision_created",
            data={
                "action": decision.action.value,
                "policy_version": decision.policy_version,
                "confidence_level": decision.confidence_level,
                "requires_human_approval": decision.requires_human_approval,
            },
            created_at=datetime.now(timezone.utc),
        )
    )


def query_decisions(
    advertisement_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> list[Decision]:
    """Query decisions from the audit trail with optional filters."""
    results = list(_decisions)
    if advertisement_id is not None:
        results = [d for d in results if d.advertisement_id == advertisement_id]
    if action is not None:
        results = [d for d in results if d.action.value == action]
    # Most recent first
    results.sort(key=lambda d: d.created_at, reverse=True)
    return results[:limit]


def query_audit_events(
    decision_id: Optional[str] = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """Query raw audit events."""
    results = list(_audit_events)
    if decision_id is not None:
        results = [e for e in results if e.decision_id == decision_id]
    results.sort(key=lambda e: e.created_at, reverse=True)
    return results[:limit]


def clear_all() -> None:
    """Clear in-memory store. Only for testing."""
    _decisions.clear()
    _audit_events.clear()
