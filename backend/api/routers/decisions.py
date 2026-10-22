"""Decisions and audit routers (stubs for Milestone 1)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_decisions():
    """List all recorded decisions (audit trail)."""
    from audit.trail import query_decisions
    decisions = query_decisions(limit=100)
    return [d.model_dump(mode="json") for d in decisions]
