"""
In-memory simulation store.

Holds the last N simulation results in memory so the API can query them
without a database in Milestone 1. PostgreSQL persistence is added in Milestone 2.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from simulator.engine import SimulationResult

# Ordered dict keyed by run_id, capped at MAX_RUNS
_runs: OrderedDict[str, SimulationResult] = OrderedDict()
MAX_RUNS = 20


def save(result: SimulationResult) -> None:
    """Save a simulation result. Evicts oldest if over capacity."""
    run_id = result.run.id
    if run_id in _runs:
        return  # idempotent — same run_id is a no-op
    _runs[run_id] = result
    while len(_runs) > MAX_RUNS:
        _runs.popitem(last=False)  # evict oldest


def get(run_id: str) -> Optional[SimulationResult]:
    return _runs.get(run_id)


def list_runs() -> list[SimulationResult]:
    return list(reversed(list(_runs.values())))  # most recent first


def clear() -> None:
    """Clear all stored runs. For testing only."""
    _runs.clear()
