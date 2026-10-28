"""
FastAPI application entry point.

Architecture rules enforced here:
- No statistical logic in this file or any router
- All business logic delegates to domain modules
- Pydantic schemas handle request/response validation
- Simulated data banner always present in responses
"""

from __future__ import annotations

import sys
import os

# Ensure backend root is on the path when running with uvicorn
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import simulations, ads, decisions, audit, health, benchmark


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify database connectivity and authoritative schema readiness without mutating schema
    try:
        from persistence.database import verify_database_schema
        verify_database_schema()
    except Exception as e:
        raise RuntimeError(f"Database readiness check failed during application startup: {e}") from e
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="QualLoop API",
    description=(
        "Uncertainty-aware lead qualification and advertising feedback system. "
        "⚠ SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, tags=["health"])
app.include_router(simulations.router, prefix="/simulations", tags=["simulations"])
app.include_router(ads.router, prefix="/ads", tags=["ads"])
app.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])
app.include_router(benchmark.router, prefix="/benchmark", tags=["benchmark"])


@app.get("/", tags=["health"])
def root():
    return {
        "service": "QualLoop API",
        "version": "0.1.0",
        "status": "ok",
        "simulated_data_only": True,
        "warning": "SIMULATED DATA — NOT CONNECTED TO A LIVE AD ACCOUNT",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docs": "/docs",
    }
