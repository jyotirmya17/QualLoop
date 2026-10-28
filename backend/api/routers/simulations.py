"""
Simulations router.

POST /simulations/run  — run a new simulation
GET  /simulations/     — list recent simulations
GET  /simulations/{id} — get a simulation run by ID
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.evaluation import evaluate_and_persist_run
from api.schemas.responses import CampaignSummaryOut, RunSimulationIn, SimulationRunOut
from api.store import save, get, list_runs
from simulator import get_scenario, run_simulation
from simulator.scenarios import SCENARIO_REGISTRY

router = APIRouter()


@router.post("/run", response_model=SimulationRunOut, status_code=201)
def run_simulation_endpoint(body: RunSimulationIn):
    """
    Run a simulation and store the result in memory.

    Returns a SimulationRun summary. Use GET /ads/run/{run_id} to retrieve
    per-ad estimates and recommendations.
    """
    if body.scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario '{body.scenario_name}'. "
                   f"Available: {list(SCENARIO_REGISTRY.keys())}",
        )

    config = get_scenario(body.scenario_name, body.seed)
    result = run_simulation(config)
    save(result)

    return SimulationRunOut(
        id=result.run.id,
        scenario_name=result.run.scenario_name,
        seed=result.run.seed,
        started_at=result.run.started_at,
        completed_at=result.run.completed_at,
        n_campaigns=result.run.n_campaigns,
        n_ads=result.run.n_ads,
        n_leads=result.run.n_leads,
    )


@router.get("/", response_model=list[SimulationRunOut])
def list_simulations():
    """List recent simulation runs (most recent first, up to 20)."""
    return [
        SimulationRunOut(
            id=r.run.id,
            scenario_name=r.run.scenario_name,
            seed=r.run.seed,
            started_at=r.run.started_at,
            completed_at=r.run.completed_at,
            n_campaigns=r.run.n_campaigns,
            n_ads=r.run.n_ads,
            n_leads=r.run.n_leads,
        )
        for r in list_runs()
    ]


@router.get("/scenarios")
def list_scenarios():
    """List all available simulation scenario presets."""
    return {"scenarios": list(SCENARIO_REGISTRY.keys())}


@router.get("/{run_id}", response_model=SimulationRunOut)
def get_simulation(run_id: str):
    result = get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Simulation run '{run_id}' not found")
    return SimulationRunOut(
        id=result.run.id,
        scenario_name=result.run.scenario_name,
        seed=result.run.seed,
        started_at=result.run.started_at,
        completed_at=result.run.completed_at,
        n_campaigns=result.run.n_campaigns,
        n_ads=result.run.n_ads,
        n_leads=result.run.n_leads,
    )


@router.post("/{run_id}/evaluate", response_model=list[CampaignSummaryOut])
def evaluate_simulation_endpoint(run_id: str):
    """
    Explicit, idempotent evaluation of a simulation run.
    Evaluates Bayesian estimates and policy decisions, persisting decisions
    and audit events to durable storage.
    """
    return evaluate_and_persist_run(run_id)
