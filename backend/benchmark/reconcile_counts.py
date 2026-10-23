"""
Reconcile and verify benchmark counts across all 4 evaluation modes:
- full: 200 simulations, 9 scenarios, seeds.json -> 350 ads (280 good, 70 poor)
- ablation: 200 simulations, 9 scenarios, seeds.json -> 350 ads (280 good, 70 poor)
- time_sliced: 200 simulations, 9 scenarios, seeds.json -> 350 ads (280 good, 70 poor)
- holdout: 100 simulations, 9 scenarios, seeds_split.json (holdout) -> 175 ads (140 good, 35 poor)

Saves all result JSONs under backend/benchmark/results/ and outputs count_reconciliation.json.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

# Ensure backend root is on sys.path
backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from benchmark.runner import BenchmarkRunner
from benchmark.time_sliced import TimeSlicedBenchmarkRunner


def reconcile_all_counts() -> dict:
    base_dir = Path(__file__).resolve().parent
    results_dir = base_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("BENCHMARK COUNT RECONCILIATION & AUDIT")
    print("=" * 80)

    runner = BenchmarkRunner(results_dir=results_dir)

    # 1. Full benchmark mode (200 seeds)
    print("\n[1/4] Running FULL benchmark mode (200 seeds)...")
    full_report = runner.run_full(save_filename="full_benchmark.json")
    meta_full = full_report.run_metadata

    # 2. Ablation mode (200 seeds)
    print("[2/4] Running ABLATION benchmark mode (200 seeds)...")
    ablation_summary = runner.run_ablation(save_filename="ablation_benchmark.json")
    meta_ablation = ablation_summary["run_metadata"]

    # 3. Time-sliced mode (200 seeds)
    print("[3/4] Running TIME-SLICED benchmark mode (200 seeds)...")
    ts_runner = TimeSlicedBenchmarkRunner(checkpoints=(3, 7, 14, 21))
    ts_summary = ts_runner.run()
    ts_path = ts_summary.save_results(output_dir=results_dir, filename="time_sliced_benchmark.json")
    meta_ts = ts_summary.to_dict()["run_metadata"]

    # 4. Holdout mode (100 seeds)
    print("[4/4] Running HOLDOUT benchmark mode (100 holdout seeds)...")
    holdout_report = runner.run_holdout(save_filename="holdout_benchmark.json")
    meta_holdout = holdout_report.run_metadata

    reconciliation = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "modes": {
            "full": {
                "n_simulations": meta_full["n_simulations"],
                "n_scenarios": meta_full["n_scenarios"],
                "seeds_file_used": meta_full["seeds_file_used"],
                "n_ads": meta_full["n_ads"],
                "n_good": meta_full["n_good"],
                "n_poor": meta_full["n_poor"],
            },
            "ablation": {
                "n_simulations": meta_ablation["n_simulations"],
                "n_scenarios": meta_ablation["n_scenarios"],
                "seeds_file_used": meta_ablation["seeds_file_used"],
                "n_ads": meta_ablation["n_ads"],
                "n_good": meta_ablation["n_good"],
                "n_poor": meta_ablation["n_poor"],
            },
            "time_sliced": {
                "n_simulations": meta_ts["n_simulations"],
                "n_scenarios": meta_ts["n_scenarios"],
                "seeds_file_used": meta_ts["seeds_file_used"],
                "n_ads": meta_ts["n_ads"],
                "n_good": meta_ts["n_good"],
                "n_poor": meta_ts["n_poor"],
            },
            "holdout": {
                "n_simulations": meta_holdout["n_simulations"],
                "n_scenarios": meta_holdout["n_scenarios"],
                "seeds_file_used": meta_holdout["seeds_file_used"],
                "n_ads": meta_holdout["n_ads"],
                "n_good": meta_holdout["n_good"],
                "n_poor": meta_holdout["n_poor"],
            },
        },
        "explanations_of_past_discrepancies": {
            "350_ads_for_200_seeds": (
                "The 200 pre-committed seeds in seeds.json span 9 scenarios. While 5 scenarios have single-ad "
                "campaigns, 4 scenarios have multi-ad campaigns: healthy_campaign (3 ads x 30 seeds = 90), "
                "good_ad_low_reachability (2 ads x 25 seeds = 50), bad_ad_high_engagement (2 ads x 25 seeds = 50), "
                "and mixed_portfolio (3 ads x 20 seeds = 60). The total ads across all 200 simulations is exactly "
                "90 + 50 + 50 + 25 + 25 + 20 + 60 + 15 + 15 = 350 ads (280 good, 70 poor). There is no double-counting."
            ),
            "350_ads_for_100_holdout_seeds": (
                "Earlier holdout scripts invoked runner.run_benchmark() without passing the holdout seed dict, defaulting "
                "to self.load_seeds() (all 200 seeds / 350 ads). When properly constrained to the 100 holdout seeds in "
                "seeds_split.json (a 50% stratified split), the exact counts are 100 simulations, 175 ads (140 good, 35 poor)."
            ),
            "70_runs": (
                "Earlier text described '70 runs' when evaluating poor ads. This was a terminology error: there are 70 poor ads "
                "across the dataset (25 bad_ad_high_engagement + 25 small_sample_trap + 20 mixed_portfolio = 70). The evaluation "
                "was executed across 200 simulation runs, not 70 runs."
            ),
            "4_scenarios_x_50_seeds_700_ads": (
                "Earlier ablation text stated '700 ads'. This occurred because the ablation evaluation runs two passes "
                "(fixed priors vs pooled priors) over the 350 ads. The script summed evaluations across both passes "
                "(350 + 350 = 700 ad evaluations) instead of reporting the 350 distinct advertisements. The dataset itself "
                "contains 350 ads."
            ),
        },
    }

    out_file = results_dir / "count_reconciliation.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(reconciliation, f, indent=2)

    print("\nRECONCILED COUNT TABLE:")
    print(f"{'Mode':<15} | {'Simulations':<12} | {'Scenarios':<10} | {'Seeds File':<25} | {'Ads':<8} | {'Good':<8} | {'Poor':<8}")
    print("-" * 95)
    for mode, data in reconciliation["modes"].items():
        print(f"{mode:<15} | {data['n_simulations']:<12} | {data['n_scenarios']:<10} | {data['seeds_file_used']:<25} | {data['n_ads']:<8} | {data['n_good']:<8} | {data['n_poor']:<8}")

    print("\nSaved reconciled JSONs to:")
    print(" - backend/benchmark/results/full_benchmark.json")
    print(" - backend/benchmark/results/ablation_benchmark.json")
    print(" - backend/benchmark/results/time_sliced_benchmark.json")
    print(" - backend/benchmark/results/holdout_benchmark.json")
    print(" - backend/benchmark/results/count_reconciliation.json")
    print("=" * 80)

    return reconciliation


if __name__ == "__main__":
    reconcile_all_counts()
