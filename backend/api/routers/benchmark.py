"""
Benchmark router.

GET  /benchmark/latest — return the most recent benchmark report
POST /benchmark/run    — trigger a benchmark run and return results
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from benchmark.runner import BenchmarkReport, BenchmarkRunner

router = APIRouter()


class BenchmarkRunIn(BaseModel):
    max_runs_per_scenario: Optional[int] = 5


@router.get("/latest")
def get_latest_benchmark():
    """Return the most recently generated benchmark report."""
    results_dir = Path(__file__).resolve().parent.parent.parent / "benchmark" / "results"
    latest_file = results_dir / "latest_benchmark.json"

    if not latest_file.exists():
        # If no benchmark run exists yet, run a fast one
        runner = BenchmarkRunner(results_dir=results_dir)
        report = runner.run_benchmark(max_runs_per_scenario=2)
        return report

    with open(latest_file, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/run")
def run_benchmark_endpoint(body: BenchmarkRunIn):
    """Trigger a benchmark run and return the structured report."""
    results_dir = Path(__file__).resolve().parent.parent.parent / "benchmark" / "results"
    runner = BenchmarkRunner(results_dir=results_dir)
    report = runner.run_benchmark(max_runs_per_scenario=body.max_runs_per_scenario)
    return report
