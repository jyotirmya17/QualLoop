"""Persistence package for QualLoop durable audit trail."""

from persistence.database import (
    get_database_url,
    get_db,
    get_engine,
    init_db,
    normalize_database_url,
    session_scope,
    set_database_url,
    verify_database_schema,
)
from persistence.models import AuditEventModel, Base, DecisionModel
from persistence.repository import (
    clear_all,
    query_audit_events,
    query_decisions,
    record_audit_event,
    record_decision,
    record_decisions,
)

__all__ = [
    "Base",
    "DecisionModel",
    "AuditEventModel",
    "get_engine",
    "get_db",
    "session_scope",
    "init_db",
    "verify_database_schema",
    "get_database_url",
    "normalize_database_url",
    "set_database_url",
    "record_decision",
    "record_decisions",
    "record_audit_event",
    "query_decisions",
    "query_audit_events",
    "clear_all",
]
