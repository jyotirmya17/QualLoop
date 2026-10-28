"""Audit trail router."""

from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/")
def get_audit_log(
    decision_id: Optional[str] = Query(None, description="Filter audit events by decision ID"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Return the audit event log from durable storage."""
    from audit.trail import query_audit_events
    events = query_audit_events(decision_id=decision_id, limit=limit)
    return [e.model_dump(mode="json") for e in events]
