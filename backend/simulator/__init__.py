"""Simulator package."""

from simulator.engine import SimulationResult, run_simulation
from simulator.scenarios import SCENARIO_REGISTRY, ScenarioConfig, get_scenario

__all__ = [
    "run_simulation",
    "SimulationResult",
    "ScenarioConfig",
    "SCENARIO_REGISTRY",
    "get_scenario",
]
