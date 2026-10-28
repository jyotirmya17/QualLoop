"""Repository functions for durable decision and audit storage."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from domain.models import AuditEvent, Decision
from persistence.database import init_db, session_scope
from persistence.models import AuditEventModel, DecisionModel


def record_decision(decision: Decision, session: Optional[Session] = None) -> None:
    """
    Append a decision and its corresponding audit event to durable storage.
    Both records are written in a single atomic transaction.
    """
    record_decisions([decision], session=session)


def record_decisions(decisions: list[Decision], session: Optional[Session] = None) -> None:
    """
    Append multiple decisions and their corresponding audit events to durable storage
    atomically within a single transaction.
    """
    def _execute(s: Session) -> None:
        now = datetime.now(timezone.utc)
        for decision in decisions:
            dec_model = DecisionModel.from_domain(decision)
            s.add(dec_model)

            audit_data = {
                "action": decision.action.value if hasattr(decision.action, "value") else str(decision.action),
                "policy_version": decision.policy_version,
                "confidence_level": decision.confidence_level,
                "requires_human_approval": decision.requires_human_approval,
                "simulation_run_id": decision.simulation_run_id,
                "advertisement_id": decision.advertisement_id,
            }
            event_model = AuditEventModel(
                decision_id=decision.id,
                event_type="decision_created",
                data=audit_data,
                created_at=now,
            )
            s.add(event_model)

    if session is not None:
        _execute(session)
    else:
        with session_scope() as s:
            _execute(s)


def record_audit_event(event: AuditEvent, session: Optional[Session] = None) -> None:
    """Persist an audit event to durable storage."""
    def _execute(s: Session) -> None:
        event_model = AuditEventModel.from_domain(event)
        s.add(event_model)

    if session is not None:
        _execute(session)
    else:
        with session_scope() as s:
            _execute(s)


def query_decisions(
    advertisement_id: Optional[str] = None,
    action: Optional[str] = None,
    simulation_run_id: Optional[str] = None,
    limit: int = 100,
    session: Optional[Session] = None,
) -> list[Decision]:
    """Query decisions from durable storage with optional filters and deterministic ordering."""
    def _execute(s: Session) -> list[Decision]:
        stmt = select(DecisionModel)
        if simulation_run_id is not None:
            stmt = stmt.where(DecisionModel.simulation_run_id == simulation_run_id)
        if advertisement_id is not None:
            stmt = stmt.where(DecisionModel.advertisement_id == advertisement_id)
        if action is not None:
            stmt = stmt.where(DecisionModel.action == action)

        stmt = stmt.order_by(DecisionModel.created_at.desc(), DecisionModel.id.desc()).limit(limit)
        models = s.scalars(stmt).all()
        return [m.to_domain() for m in models]

    if session is not None:
        return _execute(session)
    with session_scope() as s:
        return _execute(s)


def query_audit_events(
    decision_id: Optional[str] = None,
    limit: int = 100,
    session: Optional[Session] = None,
) -> list[AuditEvent]:
    """Query audit events from durable storage with deterministic ordering."""
    def _execute(s: Session) -> list[AuditEvent]:
        stmt = select(AuditEventModel)
        if decision_id is not None:
            stmt = stmt.where(AuditEventModel.decision_id == decision_id)

        stmt = stmt.order_by(AuditEventModel.created_at.desc(), AuditEventModel.id.desc()).limit(limit)
        models = s.scalars(stmt).all()
        return [m.to_domain() for m in models]

    if session is not None:
        return _execute(session)
    with session_scope() as s:
        return _execute(s)


def clear_all(session: Optional[Session] = None) -> None:
    """Clear all stored decisions and audit events. Intended for testing."""
    def _execute(s: Session) -> None:
        s.execute(delete(AuditEventModel))
        s.execute(delete(DecisionModel))

    if session is not None:
        _execute(session)
    else:
        with session_scope() as s:
            _execute(s)
