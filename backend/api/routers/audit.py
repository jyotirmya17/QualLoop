"""Audit trail router."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def get_audit_log():
    """Return the full audit event log."""
    from audit.trail import query_audit_events
    events = query_audit_events(limit=200)
    return [e.model_dump(mode="json") for e in events]
