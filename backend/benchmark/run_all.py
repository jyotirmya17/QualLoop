"""
Master Benchmark Reproduction Harness.

Single-command entry point to reproduce all QualLoop benchmark numbers:
1. Count reconciliation & standard benchmark modes (full, ablation, time-sliced, holdout)
2. Sequential closed-loop simulation (200 seeds, Day-0 Oracle)
3. Final frozen policy holdout evaluation (100 holdout seeds, paired statistical tests)
4. Continuous intent robustness benchmark (50 runs, continuous Beta intent spectrum)

Usage:
    python backend/benchmark/run_all.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from benchmark.reconcile_counts import reconcile_all_counts
from benchmark.sequential import SequentialClosedLoopRunner
from benchmark.evaluate_holdout import run_holdout_evaluation
from benchmark.robustness import run_continuous_robustness_benchmark


def run_all() -> dict[str, str]:
    print("=" * 70)
    print("QualLoop Master Benchmark Suite — Executing All Experiments")
    print("=" * 70)
    start_time = time.time()

    # 1. Count reconciliation across full, ablation, time-sliced, and holdout modes
    print("\n[1/4] Running Count Reconciliation & Multi-Mode Benchmarks...")
    t0 = time.time()
    reconciled = reconcile_all_counts()
    print(f"  -> Count Reconciliation completed in {time.time() - t0:.2f}s")

    # 2. Sequential closed-loop simulation across 200 seeds (both variable and fixed budget)
    print("\n[2/5] Running Sequential Closed-Loop Benchmarks (200 seeds, Variable & Fixed)...")
    t0 = time.time()
    seq_runner = SequentialClosedLoopRunner()
    seq_res_var = seq_runner.run_benchmark(save_filename="sequential_closed_loop.json", budget_mode="variable")
    seq_res_fixed = seq_runner.run_benchmark(save_filename="sequential_fixed_budget.json", budget_mode="fixed_redistributed")
    print(f"  -> Sequential Closed-Loop completed in {time.time() - t0:.2f}s")

    # 3. Final frozen policy evaluation on 100 holdout seeds (both budget modes)
    print("\n[3/5] Running Holdout Evaluation on Frozen Policy (100 holdout seeds, 5 policies)...")
    t0 = time.time()
    holdout_res = run_holdout_evaluation(save_filename="holdout_sequential.json")
    print(f"  -> Holdout Evaluation completed in {time.time() - t0:.2f}s")

    # 4. Continuous intent robustness benchmark
    print("\n[4/5] Running Continuous Intent Robustness Benchmark (50 runs)...")
    t0 = time.time()
    robustness_res = run_continuous_robustness_benchmark(save_filename="robustness_benchmark.json")
    print(f"  -> Continuous Robustness completed in {time.time() - t0:.2f}s")

    # 5. Tuning reproduction and honest selection rule audit
    print("\n[5/5] Running Tuning Table Reproduction & Audit (100 tuning seeds)...")
    t0 = time.time()
    from benchmark.reproduce_tuning import reproduce_tuning_table
    tuning_res = reproduce_tuning_table()
    print(f"  -> Tuning Reproduction completed in {time.time() - t0:.2f}s")

    total_elapsed = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"All benchmarks executed successfully in {total_elapsed:.2f}s!")
    print("Results saved in backend/benchmark/results/:")
    results_dir = Path(__file__).resolve().parent / "results"
    for p in sorted(results_dir.glob("*.json")):
        print(f"  - {p.name} ({p.stat().st_size} bytes)")
    print("=" * 70)

    return {
        "count_reconciliation": "backend/benchmark/results/count_reconciliation.json",
        "sequential_closed_loop": "backend/benchmark/results/sequential_closed_loop.json",
        "holdout_sequential": "backend/benchmark/results/holdout_sequential.json",
        "robustness_benchmark": "backend/benchmark/results/robustness_benchmark.json",
    }


if __name__ == "__main__":
    run_all()
