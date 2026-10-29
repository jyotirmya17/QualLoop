"""
Export real decision records across governance tiers.

Runs real simulations, evaluates campaign Bayesian posteriors and decision rules,
and prints one real decision record per tier (autonomous, within_guardrails, gated)
with full provenance metadata:
- scenario
- seed
- run_id
- advertisement_id
- creative_id
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_root = Path(__file__).resolve().parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# Ensure UTF-8 output on all platforms (including Windows consoles)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from api.evaluation import compute_analysis_for_run
from simulator import get_scenario, run_simulation


def export_decisions():
    # Primary scenario: mixed_portfolio (seed 42)
    primary_scenario = "mixed_portfolio"
    primary_seed = 42
    primary_config = get_scenario(primary_scenario, primary_seed)
    primary_result = run_simulation(primary_config)
    primary_summaries, primary_decisions = compute_analysis_for_run(primary_result)

    decisions_by_tier = {}
    metadata_by_tier = {}

    for summary in primary_summaries:
        for ad_analysis in summary.ads:
            tier = ad_analysis.decision.tier
            if tier not in decisions_by_tier:
                decisions_by_tier[tier] = ad_analysis.decision
                metadata_by_tier[tier] = {
                    "scenario": primary_scenario,
                    "seed": primary_seed,
                    "run_id": primary_result.run.id,
                    "advertisement_id": ad_analysis.advertisement.id,
                    "creative_id": ad_analysis.advertisement.creative_id,
                }

    # If 'gated' did not emerge in mixed_portfolio, run healthy_campaign (seed 42)
    if "gated" not in decisions_by_tier:
        fallback_scenario = "healthy_campaign"
        fallback_seed = 42
        fallback_config = get_scenario(fallback_scenario, fallback_seed)
        fallback_result = run_simulation(fallback_config)
        fallback_summaries, fallback_decisions = compute_analysis_for_run(fallback_result)

        for summary in fallback_summaries:
            for ad_analysis in summary.ads:
                if ad_analysis.decision.tier == "gated" and "gated" not in decisions_by_tier:
                    decisions_by_tier["gated"] = ad_analysis.decision
                    metadata_by_tier["gated"] = {
                        "scenario": fallback_scenario,
                        "seed": fallback_seed,
                        "run_id": fallback_result.run.id,
                        "advertisement_id": ad_analysis.advertisement.id,
                        "creative_id": ad_analysis.advertisement.creative_id,
                    }
                    break

    ordered_tiers = ["autonomous", "within_guardrails", "gated"]
    exported_records = {}

    for tier in ordered_tiers:
        dec = decisions_by_tier.get(tier)
        meta = metadata_by_tier.get(tier)
        if not dec or not meta:
            continue

        raw_json = json.loads(dec.model_dump_json())
        exported_records[tier] = {
            "metadata": meta,
            "decision": raw_json,
        }

        print("=" * 80)
        print(f"TIER: {tier.upper()}")
        print(f"Scenario: {meta['scenario']}")
        print(f"Seed: {meta['seed']}")
        print(f"Run ID: {meta['run_id']}")
        print(f"Advertisement ID: {meta['advertisement_id']}")
        print(f"Creative ID: {meta['creative_id']}")
        print("-" * 80)
        print(json.dumps(raw_json, indent=2, ensure_ascii=False))
        print("=" * 80 + "\n")

    return exported_records


if __name__ == "__main__":
    export_decisions()
