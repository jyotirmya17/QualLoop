"""Health check router."""

from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "simulated_data_only": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
