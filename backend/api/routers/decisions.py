from typing import Optional

from fastapi import APIRouter, Query

from api.schemas.responses import DecisionOut

router = APIRouter()


@router.get("/", response_model=list[DecisionOut])
def list_decisions(
    simulation_run_id: Optional[str] = Query(None, description="Filter by simulation run ID"),
    advertisement_id: Optional[str] = Query(None, description="Filter by advertisement ID"),
    action: Optional[str] = Query(None, description="Filter by decision action"),
    limit: int = Query(100, ge=1, le=1000),
):
    """List recorded decisions from durable storage with optional filtering."""
    from audit.trail import query_decisions
    decisions = query_decisions(
        simulation_run_id=simulation_run_id,
        advertisement_id=advertisement_id,
        action=action,
        limit=limit,
    )
    return [DecisionOut(**d.model_dump()) for d in decisions]
