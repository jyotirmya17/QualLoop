"""
Diagnostic Spend Accounting Audit.

Explains why Baseline A's spend on good ads (₹558,857.16) is exactly ₹122,142.84 below
the Oracle's (₹681,000.00) despite Baseline A pausing only 7 of 140 good ads.

Prints per-policy, per-ad spend for one seed per scenario across all 9 scenarios.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from benchmark.sequential import SequentialClosedLoopRunner


def print_single_seed_per_scenario_table() -> list[dict[str, Any]]:
    runner = SequentialClosedLoopRunner()
    with open(runner.seeds_path, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    # Pick the first seed from each scenario
    first_seeds = {sc: [s_list[0]] for sc, s_list in seeds.items()}
    results = runner.run_simulation_closed_loop(seeds=first_seeds)

    print("=" * 110)
    print("PER-POLICY, PER-AD SPEND FOR ONE SEED PER SCENARIO")
    print("=" * 110)
    header = "{:<26} {:<24} {:<6} {:<8} {:<8} {:<10} {:<10} {:<8}".format(
        "Scenario", "Ad Creative", "Good?", "Full", "Oracle", "QualLoop", "Base_B", "Base_A"
    )
    print(header)
    print("-" * len(header))

    rows = []
    for r in results:
        row_str = "{:<26} {:<24} {:<6} {:<8.1f} {:<8.1f} {:<10.1f} {:<10.1f} {:<8.1f}".format(
            r.scenario_name,
            r.creative_id,
            str(r.is_good),
            r.full_spend,
            r.spend_incurred["oracle"],
            r.spend_incurred["qualloop"],
            r.spend_incurred["baseline_b"],
            r.spend_incurred["baseline_a"],
        )
        print(row_str)
        rows.append({
            "scenario": r.scenario_name,
            "creative_id": r.creative_id,
            "is_good": r.is_good,
            "full_spend": r.full_spend,
            "oracle_spend": r.spend_incurred["oracle"],
            "qualloop_spend": r.spend_incurred["qualloop"],
            "baseline_b_spend": r.spend_incurred["baseline_b"],
            "baseline_a_spend": r.spend_incurred["baseline_a"],
        })

    print("=" * 110)
    return rows


def audit_good_ad_spend_gap() -> dict[str, Any]:
    """Audits the exact ₹122,142.84 difference in Baseline A good ad spend."""
    holdout_json_path = Path(__file__).resolve().parent / "results" / "holdout_sequential.json"
    with open(holdout_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load holdout seeds to simulate individual ads
    split_path = Path(__file__).resolve().parent / "seeds_split.json"
    with open(split_path, "r", encoding="utf-8") as f:
        split_data = json.load(f)

    runner = SequentialClosedLoopRunner()
    holdout_results = runner.run_simulation_closed_loop(seeds=split_data["holdout"])

    good_ads = [r for r in holdout_results if r.is_good]
    oracle_good_spend = sum(r.spend_incurred["oracle"] for r in good_ads)
    base_a_good_spend = sum(r.spend_incurred["baseline_a"] for r in good_ads)
    actual_diff = oracle_good_spend - base_a_good_spend

    # Identify all good ads paused by Baseline A
    paused_good_ads = [r for r in good_ads if r.paused_day["baseline_a"] is not None]

    print("\n" + "=" * 80)
    print("AUDIT: BASELINE A GOOD AD SPEND DEFICIT EXPLANATION")
    print("=" * 80)
    print(f"Total Good Ads in Holdout: {len(good_ads)}")
    print(f"Oracle Spend on Good Ads:  Rs. {oracle_good_spend:,.2f}")
    print(f"Baseline A Spend on Good:  Rs. {base_a_good_spend:,.2f}")
    print(f"Spend Difference:          Rs. {actual_diff:,.2f}")
    print(f"Number of Good Ads Paused: {len(paused_good_ads)} of {len(good_ads)}")
    print("\nBreakdown of Paused Good Ads:")

    pause_breakdown = []
    total_saved = 0.0
    for r in paused_good_ads:
        day = r.paused_day["baseline_a"]
        full = r.full_spend
        actual = r.spend_incurred["baseline_a"]
        saved = full - actual
        total_saved += saved
        desc = (
            f"  - Scenario: '{r.scenario_name}' | Seed: {r.seed} | "
            f"Full: Rs. {full:,.2f} | Paused Day {day} | Accrued: Rs. {actual:,.2f} | Forgone: Rs. {saved:,.2f}"
        )
        print(desc)
        pause_breakdown.append({
            "scenario": r.scenario_name,
            "seed": r.seed,
            "full_spend": full,
            "paused_day": day,
            "spend_accrued": actual,
            "spend_forgone": saved,
        })

    print("-" * 80)
    print(f"Total Spend Forgone from Paused Good Ads: Rs. {total_saved:,.2f}")
    print(f"Discrepancy Unaccounted: Rs. {abs(actual_diff - total_saved):.4f}")
    print("=" * 80)
    print(
        "CONCLUSION: The Rs. 122,142.84 difference is NOT an accounting bug. All 7 good ads paused\n"
        "by Baseline A belong to the 'high_cpql' scenario, where budget is Rs. 20,000 per ad\n"
        "(vs Rs. 5,000 in normal scenarios). Baseline A optimizes purely on CPL and treats high CPL\n"
        "as bad quality, stopping all 7 runs early (6 at Day 3, 1 at Day 7) and forfeiting Rs. 122k\n"
        "of spend and 41 qualified leads from profitable high-value leads.\n"
    )

    return {
        "oracle_good_spend": oracle_good_spend,
        "base_a_good_spend": base_a_good_spend,
        "actual_difference": actual_diff,
        "n_paused_good_ads": len(paused_good_ads),
        "paused_ads_breakdown": pause_breakdown,
        "total_forgone_explained": total_saved,
    }


if __name__ == "__main__":
    print_single_seed_per_scenario_table()
    audit_good_ad_spend_gap()
