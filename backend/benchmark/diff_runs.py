"""
Run run_all.py twice and perform a strict diff of all result JSON files.
"""

import copy
import json
import subprocess
import sys
from pathlib import Path


def strip_timestamps(obj):
    """Recursively remove non-deterministic timestamp fields for byte-equivalent semantic comparison."""
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k in ("executed_at", "started_at", "completed_at", "audit_timestamp", "timestamp"):
                continue
            new_obj[k] = strip_timestamps(v)
        return new_obj
    elif isinstance(obj, list):
        return [strip_timestamps(i) for i in obj]
    else:
        return obj


def main():
    backend_dir = Path(__file__).resolve().parent.parent
    results_dir = backend_dir / "benchmark" / "results"

    print("=================================================================")
    print("STEP 1: Executing run_all.py (First Pass)...")
    print("=================================================================")
    subprocess.run([sys.executable, str(backend_dir / "benchmark" / "run_all.py")], check=True, cwd=str(backend_dir))

    # Snapshot all JSONs
    snapshot_1 = {}
    for p in results_dir.glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            snapshot_1[p.name] = json.load(f)

    print("\n=================================================================")
    print("STEP 2: Executing run_all.py (Second Pass)...")
    print("=================================================================")
    subprocess.run([sys.executable, str(backend_dir / "benchmark" / "run_all.py")], check=True, cwd=str(backend_dir))

    snapshot_2 = {}
    for p in results_dir.glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            snapshot_2[p.name] = json.load(f)

    CANONICAL_FILES = [
        "full_benchmark.json",
        "ablation_benchmark.json",
        "time_sliced_benchmark.json",
        "holdout_benchmark.json",
        "latest_benchmark.json",
        "sequential_closed_loop.json",
        "sequential_fixed_budget.json",
        "holdout_sequential.json",
        "robustness_benchmark.json",
        "tuning_reproduction.json",
        "baseline_c_tuning.json",
        "count_reconciliation.json",
    ]

    print("\n=================================================================")
    print("STEP 3: Diffing Canonical Result JSONs across Pass 1 and Pass 2...")
    print("=================================================================")

    diffs_found = False

    for name in CANONICAL_FILES:
        if name not in snapshot_1 or name not in snapshot_2:
            print(f"  [MISSING] {name} is missing from one of the passes!")
            diffs_found = True
            continue

        clean_1 = strip_timestamps(snapshot_1[name])
        clean_2 = strip_timestamps(snapshot_2[name])

        str_1 = json.dumps(clean_1, sort_keys=True, indent=2)
        str_2 = json.dumps(clean_2, sort_keys=True, indent=2)

        if str_1 == str_2:
            print(f"  [BYTE-IDENTICAL] {name:30s} -> Exact match across runs ({len(str_1)} chars)")
        else:
            diffs_found = True
            print(f"  [DIFF DETECTED]  {name:30s} -> Differs between Pass 1 and Pass 2!")

    if not diffs_found:
        print("\nSUCCESS: All benchmark result JSONs are 100% deterministic and byte-identical across runs (excluding execution timestamps).")
    else:
        print("\nFAILURE: Differences detected across runs.")


if __name__ == "__main__":
    main()
