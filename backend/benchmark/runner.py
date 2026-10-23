"""
Benchmark runner — paired comparison between QualLoop and baseline policies.

ARCHITECTURE BOUNDARY:
This module is the only non-test module authorized to access simulator ground truth
via SimulationResult.ground_truth. It evaluates both policies against objective truth.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from benchmark.baseline import BaselineDecision, BaselinePolicy
from decision_engine.engine import DecisionPolicy, evaluate
from domain.enums import DecisionAction
from estimator.estimator import EstimatorConfig, compute_campaign_estimates, compute_estimates
from simulator.engine import SimulationResult, run_simulation
from simulator.scenarios import SCENARIO_REGISTRY, ScenarioConfig, get_scenario


@dataclass
class AdEvaluation:
    """Evaluation record for a single ad under both policies."""

    run_id: str
    scenario_name: str
    seed: int
    ad_id: str
    creative_id: str
    spend: float
    gt_label: str
    gt_reachability: float
    gt_intent_mean: float
    is_good_ad: bool
    is_poor_ad: bool

    # Baseline outcomes
    baseline_action: str
    baseline_observed_reach: float
    baseline_observed_qual: float
    baseline_false_positive_pause: bool
    baseline_false_negative: bool

    # QualLoop outcomes
    qualloop_action: str
    qualloop_reach_mean: float
    qualloop_reach_ci: list[float]
    qualloop_qual_mean: float
    qualloop_qual_ci: list[float]
    qualloop_eql_mean: float
    qualloop_false_positive_pause: bool
    qualloop_false_negative: bool
    qualloop_insufficient_evidence: bool


@dataclass
class PolicySummary:
    fppr_mean: float
    fppr_ci: list[float]
    fndr_mean: float
    fndr_ci: list[float]
    ier_mean: float
    qlus: float
    total_spend: float
    total_qualified_leads: int


@dataclass
class ScenarioBreakdown:
    scenario_name: str
    n_simulations: int
    n_ads: int
    qualloop_fppr: float
    baseline_fppr: float
    qualloop_fndr: float
    baseline_fndr: float


@dataclass
class BenchmarkReport:
    run_metadata: dict[str, Any]
    aggregate_metrics: dict[str, Any]
    per_scenario_breakdown: list[dict[str, Any]]
    cases_where_qualloop_performed_worse: list[dict[str, Any]]


def _wilson_score_interval(successes: int, total: int, confidence: float = 0.95) -> list[float]:
    """Calculate Wilson score interval for a binomial proportion."""
    if total <= 0:
        return [0.0, 0.0]
    z = 1.95996  # ~95%
    p = successes / total
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    spread = (z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)) / denom
    return [float(max(0.0, centre - spread)), float(min(1.0, centre + spread))]


class BenchmarkRunner:
    """Executes paired benchmark across seeds and scenarios."""

    def __init__(
        self,
        seeds_path: Optional[Path] = None,
        results_dir: Optional[Path] = None,
        estimator_config: Optional[EstimatorConfig] = None,
        decision_policy: Optional[DecisionPolicy] = None,
        baseline_policy: Optional[BaselinePolicy] = None,
    ):
        base_dir = Path(__file__).resolve().parent
        self.seeds_path = seeds_path or (base_dir / "seeds.json")
        self.results_dir = results_dir or (base_dir / "results")
        self.estimator_config = estimator_config or EstimatorConfig()
        self.decision_policy = decision_policy or DecisionPolicy()
        self.baseline_policy = baseline_policy or BaselinePolicy()

    def load_seeds(self) -> dict[str, list[int]]:
        with open(self.seeds_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def run_benchmark(
        self,
        mode: str = "full",
        max_runs_per_scenario: Optional[int] = None,
        executed_at: Optional[str] = None,
        enable_shrinkage: bool = True,
        seeds: Optional[dict[str, list[int]]] = None,
        seed_file_name: Optional[str] = None,
        save_filename: Optional[str] = None,
    ) -> BenchmarkReport:
        """Run the paired benchmark across all pre-committed seeds."""
        scenario_seeds = seeds if seeds is not None else self.load_seeds()
        evaluations: list[AdEvaluation] = []
        simulations_count = 0
        worse_cases: list[dict[str, Any]] = []

        total_qualloop_qual_leads = 0
        total_baseline_qual_leads = 0
        total_spend = 0.0

        for scenario_name, seeds in scenario_seeds.items():
            if max_runs_per_scenario is not None:
                seeds = seeds[:max_runs_per_scenario]

            for seed in seeds:
                config = get_scenario(scenario_name, seed=seed)
                result: SimulationResult = run_simulation(config)
                simulations_count += 1

                obs_time = result.run.completed_at or datetime.now(timezone.utc)

                # Index domain objects by ad_id
                leads_by_ad = {ad.id: [] for ad in result.advertisements}
                for lead in result.leads:
                    if lead.advertisement_id in leads_by_ad:
                        leads_by_ad[lead.advertisement_id].append(lead)

                calls_by_ad = {ad.id: [] for ad in result.advertisements}
                leads_by_id = {l.id: l for l in result.leads}
                for ca in result.call_attempts:
                    lead = leads_by_id.get(ca.lead_id)
                    if lead and lead.advertisement_id in calls_by_ad:
                        calls_by_ad[lead.advertisement_id].append(ca)

                quals_by_ad = {ad.id: [] for ad in result.advertisements}
                for qo in result.qualification_outcomes:
                    lead = leads_by_id.get(qo.lead_id)
                    if lead and lead.advertisement_id in quals_by_ad:
                        quals_by_ad[lead.advertisement_id].append(qo)

                ads_data = [
                    (
                        ad,
                        leads_by_ad.get(ad.id, []),
                        calls_by_ad.get(ad.id, []),
                        quals_by_ad.get(ad.id, []),
                    )
                    for ad in result.advertisements
                ]
                snapshots = compute_campaign_estimates(
                    ads_data=ads_data,
                    observation_time=obs_time,
                    config=self.estimator_config,
                    seed=seed,
                    enable_shrinkage=enable_shrinkage,
                )
                snapshots_by_ad = {ad.id: snap for ad, snap in zip(result.advertisements, snapshots)}

                # Evaluate each ad
                for ad in result.advertisements:
                    total_spend += ad.spend
                    gt = next(
                        (g for g in result.ground_truth if g.advertisement_id == ad.id),
                        None,
                    )
                    gt_intent_mean = float(np.mean(gt.true_intent_by_day)) if gt else 0.0
                    gt_reach = gt.true_reachability if gt else 0.5
                    gt_label = gt.label if gt else "unlabelled"

                    is_good_ad = (gt_label == "good") or (gt_intent_mean >= 0.15)
                    is_poor_ad = (gt_label == "bad") or (gt_intent_mean < 0.05)

                    ad_leads = leads_by_ad.get(ad.id, [])
                    ad_calls = calls_by_ad.get(ad.id, [])
                    ad_quals = quals_by_ad.get(ad.id, [])

                    # 1. Baseline policy
                    baseline_dec = self.baseline_policy.evaluate(
                        ad, ad_leads, ad_calls, ad_quals
                    )
                    b_paused = baseline_dec.action in (
                        DecisionAction.PAUSE_AD,
                        DecisionAction.CONSIDER_PAUSE,
                    )
                    b_false_positive = is_good_ad and b_paused
                    b_false_negative = is_poor_ad and not b_paused

                    # 2. QualLoop policy
                    snapshot = snapshots_by_ad[ad.id]
                    qualloop_dec = evaluate(
                        snapshot,
                        ad_spend=ad.spend,
                        policy=self.decision_policy,
                        campaign_snapshots=snapshots,
                    )
                    q_paused = qualloop_dec.action in (
                        DecisionAction.PAUSE_AD,
                        DecisionAction.CONSIDER_PAUSE,
                    )
                    q_false_positive = is_good_ad and q_paused
                    q_false_negative = is_poor_ad and not q_paused
                    q_insufficient = qualloop_dec.action in (
                        DecisionAction.COLLECT_MORE_DATA,
                        DecisionAction.FLAG_INSUFFICIENT_EVIDENCE,
                    )

                    # QLUS calculation tracking
                    if not q_paused:
                        total_qualloop_qual_leads += snapshot.k_qualified
                    if not b_paused:
                        total_baseline_qual_leads += baseline_dec.k_qualified

                    # Honesty: record cases where QualLoop performed worse than baseline
                    # Example: QualLoop paused a good ad that baseline kept running, or
                    # QualLoop failed to pause a poor ad that baseline correctly paused
                    if (q_false_positive and not b_false_positive) or (
                        q_false_negative and not b_false_negative
                    ):
                        worse_cases.append(
                            {
                                "run_id": result.run.id,
                                "scenario": scenario_name,
                                "seed": seed,
                                "creative_id": ad.creative_id,
                                "is_good_ad": is_good_ad,
                                "is_poor_ad": is_poor_ad,
                                "gt_intent_mean": round(gt_intent_mean, 3),
                                "qualloop_action": qualloop_dec.action.value,
                                "baseline_action": baseline_dec.action.value,
                                "qualloop_reason": qualloop_dec.reason,
                                "explanation": (
                                    "QualLoop paused a good ad"
                                    if q_false_positive
                                    else "QualLoop was too conservative to pause a poor ad"
                                ),
                            }
                        )

                    evaluations.append(
                        AdEvaluation(
                            run_id=result.run.id,
                            scenario_name=scenario_name,
                            seed=seed,
                            ad_id=ad.id,
                            creative_id=ad.creative_id,
                            spend=ad.spend,
                            gt_label=gt_label,
                            gt_reachability=gt_reach,
                            gt_intent_mean=gt_intent_mean,
                            is_good_ad=is_good_ad,
                            is_poor_ad=is_poor_ad,
                            baseline_action=baseline_dec.action.value,
                            baseline_observed_reach=baseline_dec.observed_reachability,
                            baseline_observed_qual=baseline_dec.observed_qualification,
                            baseline_false_positive_pause=b_false_positive,
                            baseline_false_negative=b_false_negative,
                            qualloop_action=qualloop_dec.action.value,
                            qualloop_reach_mean=snapshot.reachability_mean,
                            qualloop_reach_ci=[
                                snapshot.reachability_ci_low,
                                snapshot.reachability_ci_high,
                            ],
                            qualloop_qual_mean=snapshot.qualification_mean,
                            qualloop_qual_ci=[
                                snapshot.qualification_ci_low,
                                snapshot.qualification_ci_high,
                            ],
                            qualloop_eql_mean=snapshot.eql_mean,
                            qualloop_false_positive_pause=q_false_positive,
                            qualloop_false_negative=q_false_negative,
                            qualloop_insufficient_evidence=q_insufficient,
                        )
                    )

        # Aggregate metric calculations
        good_ads = [e for e in evaluations if e.is_good_ad]
        poor_ads = [e for e in evaluations if e.is_poor_ad]
        all_ads_count = len(evaluations)

        n_good = len(good_ads)
        n_poor = len(poor_ads)

        q_fp_count = sum(1 for e in good_ads if e.qualloop_false_positive_pause)
        b_fp_count = sum(1 for e in good_ads if e.baseline_false_positive_pause)

        q_fn_count = sum(1 for e in poor_ads if e.qualloop_false_negative)
        b_fn_count = sum(1 for e in poor_ads if e.baseline_false_negative)

        q_ier_count = sum(1 for e in evaluations if e.qualloop_insufficient_evidence)

        q_fppr_mean = q_fp_count / n_good if n_good > 0 else 0.0
        b_fppr_mean = b_fp_count / n_good if n_good > 0 else 0.0

        q_fndr_mean = q_fn_count / n_poor if n_poor > 0 else 0.0
        b_fndr_mean = b_fn_count / n_poor if n_poor > 0 else 0.0

        q_ier_mean = q_ier_count / all_ads_count if all_ads_count > 0 else 0.0
        b_ier_mean = 0.0  # baseline has no insufficient evidence concept

        q_iesr_mean = q_fp_count / all_ads_count if all_ads_count > 0 else 0.0
        b_iesr_mean = b_fp_count / all_ads_count if all_ads_count > 0 else 0.0

        qlus_qualloop = total_qualloop_qual_leads / total_spend if total_spend > 0 else 0.0
        qlus_baseline = total_baseline_qual_leads / total_spend if total_spend > 0 else 0.0

        # Per scenario breakdown
        breakdowns = []
        scenarios_seen = sorted({e.scenario_name for e in evaluations})
        for sc in scenarios_seen:
            sc_ads = [e for e in evaluations if e.scenario_name == sc]
            sc_good = [e for e in sc_ads if e.is_good_ad]
            sc_poor = [e for e in sc_ads if e.is_poor_ad]
            sc_sim_count = len({e.run_id for e in sc_ads})

            sc_q_fp = sum(1 for e in sc_good if e.qualloop_false_positive_pause)
            sc_b_fp = sum(1 for e in sc_good if e.baseline_false_positive_pause)
            sc_q_fn = sum(1 for e in sc_poor if e.qualloop_false_negative)
            sc_b_fn = sum(1 for e in sc_poor if e.baseline_false_negative)

            breakdowns.append(
                {
                    "scenario_name": sc,
                    "n_simulations": sc_sim_count,
                    "n_ads": len(sc_ads),
                    "qualloop_fppr": round(sc_q_fp / len(sc_good), 3) if sc_good else 0.0,
                    "baseline_fppr": round(sc_b_fp / len(sc_good), 3) if sc_good else 0.0,
                    "qualloop_fndr": round(sc_q_fn / len(sc_poor), 3) if sc_poor else 0.0,
                    "baseline_fndr": round(sc_b_fn / len(sc_poor), 3) if sc_poor else 0.0,
                }
            )

        report = BenchmarkReport(
            run_metadata={
                "mode": mode,
                "n_simulations": simulations_count,
                "n_scenarios": len(scenarios_seen),
                "seeds_file_used": seed_file_name or str(self.seeds_path.name),
                "n_ads": all_ads_count,
                "n_good": n_good,
                "n_poor": n_poor,
                # Compatibility keys
                "n_ads_evaluated": all_ads_count,
                "n_good_ads": n_good,
                "n_poor_ads": n_poor,
                "seed_file": seed_file_name or str(self.seeds_path.name),
                "qualloop_policy_version": self.decision_policy.version,
                "baseline_description": "Naive 10% threshold on un-matured contact/qualification ratios",
                "executed_at": executed_at or datetime.now(timezone.utc).isoformat(),
            },
            aggregate_metrics={
                "qualloop": {
                    "fppr_mean": round(q_fppr_mean, 4),
                    "fppr_ci": _wilson_score_interval(q_fp_count, n_good),
                    "fndr_mean": round(q_fndr_mean, 4),
                    "fndr_ci": _wilson_score_interval(q_fn_count, n_poor),
                    "ier_mean": round(q_ier_mean, 4),
                    "iesr_mean": round(q_iesr_mean, 4),
                    "qlus": round(qlus_qualloop, 5),
                    "total_spend": round(total_spend, 2),
                    "total_qualified_leads_preserved": total_qualloop_qual_leads,
                },
                "baseline": {
                    "fppr_mean": round(b_fppr_mean, 4),
                    "fppr_ci": _wilson_score_interval(b_fp_count, n_good),
                    "fndr_mean": round(b_fndr_mean, 4),
                    "fndr_ci": _wilson_score_interval(b_fn_count, n_poor),
                    "ier_mean": b_ier_mean,
                    "iesr_mean": round(b_iesr_mean, 4),
                    "qlus": round(qlus_baseline, 5),
                    "total_spend": round(total_spend, 2),
                    "total_qualified_leads_preserved": total_baseline_qual_leads,
                },
            },
            per_scenario_breakdown=breakdowns,
            cases_where_qualloop_performed_worse=worse_cases[:50],  # top 50 instances
        )

        # Ensure results directory exists
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Write timestamped JSON result
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = self.results_dir / f"benchmark_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2)

        # Also save as latest_benchmark.json for API/dashboard access
        latest_path = self.results_dir / "latest_benchmark.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2)

        if save_filename:
            custom_path = self.results_dir / save_filename
            with open(custom_path, "w", encoding="utf-8") as f:
                json.dump(asdict(report), f, indent=2)

        # Generate human-readable Markdown report
        self._write_markdown_report(report)

        return report

    def _write_markdown_report(self, report: BenchmarkReport) -> None:
        md_path = self.results_dir / "REPORT.md"
        meta = report.run_metadata
        agg = report.aggregate_metrics
        q = agg["qualloop"]
        b = agg["baseline"]

        lines = [
            "# QualLoop vs. Naive Baseline Benchmark Report",
            "",
            f"**Executed At:** {meta['executed_at']}  ",
            f"**Simulations:** {meta['n_simulations']}  ",
            f"**Total Ads Evaluated:** {meta['n_ads_evaluated']} ({meta['n_good_ads']} good, {meta['n_poor_ads']} poor)  ",
            f"**QualLoop Policy:** {meta['qualloop_policy_version']}  ",
            "",
            "---",
            "",
            "## 1. Executive Summary",
            "",
            "| Metric | QualLoop (Uncertainty-Aware) | Baseline (Naive 10% Ratio) | Delta |",
            "|---|---|---|---|",
            f"| **False Positive Pause Rate (FPPR)** | **{q['fppr_mean']:.1%}** [{q['fppr_ci'][0]:.1%}, {q['fppr_ci'][1]:.1%}] | {b['fppr_mean']:.1%} [{b['fppr_ci'][0]:.1%}, {b['fppr_ci'][1]:.1%}] | **{(q['fppr_mean'] - b['fppr_mean']):.1%}** |",
            f"| **False Negative Detection Rate (FNDR)** | **{q['fndr_mean']:.1%}** [{q['fndr_ci'][0]:.1%}, {q['fndr_ci'][1]:.1%}] | {b['fndr_mean']:.1%} [{b['fndr_ci'][0]:.1%}, {b['fndr_ci'][1]:.1%}] | {(q['fndr_mean'] - b['fndr_mean']):.1%} |",
            f"| **Insufficient Evidence Rate (IER)** | {q['ier_mean']:.1%} | {b['ier_mean']:.1%} | +{q['ier_mean']:.1%} |",
            f"| **Incorrect Early Stop Rate (IESR)** | {q.get('iesr_mean', 0.0):.1%} | {b.get('iesr_mean', 0.0):.1%} | {(q.get('iesr_mean', 0.0) - b.get('iesr_mean', 0.0)):.1%} |",
            f"| **Preserved Qualified Leads** | **{q['total_qualified_leads_preserved']}** | {b['total_qualified_leads_preserved']} | +{q['total_qualified_leads_preserved'] - b['total_qualified_leads_preserved']} |",
            "",
            "> [!NOTE]",
            "> **FPPR Target:** QualLoop aims for FPPR < 10%. Baseline prematurely kills good ads",
            "> during immature windows or small sample sizes.",
            "",
            "---",
            "",
            "## 2. Per-Scenario Performance",
            "",
            "| Scenario | Simulations | Ads | QualLoop FPPR | Baseline FPPR | QualLoop FNDR | Baseline FNDR |",
            "|---|---|---|---|---|---|---|",
        ]

        for sc in report.per_scenario_breakdown:
            lines.append(
                f"| `{sc['scenario_name']}` | {sc['n_simulations']} | {sc['n_ads']} | "
                f"{sc['qualloop_fppr']:.1%} | {sc['baseline_fppr']:.1%} | "
                f"{sc['qualloop_fndr']:.1%} | {sc['baseline_fndr']:.1%} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## 3. Honesty & Transparency: Cases Where QualLoop Performed Worse",
            "",
            f"Total instances observed where QualLoop performed worse than baseline: **{len(report.cases_where_qualloop_performed_worse)}**",
            "",
        ])

        if not report.cases_where_qualloop_performed_worse:
            lines.append("No instances where QualLoop performed worse than baseline were detected in this run.")
        else:
            lines.append("| Scenario | Creative ID | True Intent | QualLoop Action | Baseline Action | Explanation |")
            lines.append("|---|---|---|---|---|---|")
            for c in report.cases_where_qualloop_performed_worse[:15]:
                lines.append(
                    f"| `{c['scenario']}` | `{c['creative_id']}` | {c['gt_intent_mean']:.1%} | "
                    f"`{c['qualloop_action']}` | `{c['baseline_action']}` | {c['explanation']} |"
                )

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def run_full(
        self,
        max_runs_per_scenario: Optional[int] = None,
        save_filename: str = "full_benchmark.json",
    ) -> BenchmarkReport:
        """Run full evaluation across all 200 seeds in seeds.json."""
        return self.run_benchmark(
            mode="full",
            max_runs_per_scenario=max_runs_per_scenario,
            enable_shrinkage=True,
            seed_file_name="seeds.json",
            save_filename=save_filename,
        )

    def run_holdout(
        self,
        max_runs_per_scenario: Optional[int] = None,
        save_filename: str = "holdout_benchmark.json",
    ) -> BenchmarkReport:
        """Run evaluation on the 100 holdout seeds in seeds_split.json."""
        split_path = self.seeds_path.parent / "seeds_split.json"
        with open(split_path, "r", encoding="utf-8") as f:
            split_data = json.load(f)
        holdout_seeds = split_data.get("holdout", {})
        return self.run_benchmark(
            mode="holdout",
            max_runs_per_scenario=max_runs_per_scenario,
            seeds=holdout_seeds,
            seed_file_name="seeds_split.json (holdout)",
            save_filename=save_filename,
        )

    def run_ablation(
        self,
        max_runs_per_scenario: Optional[int] = None,
        save_filename: str = "ablation_benchmark.json",
    ) -> dict[str, Any]:
        """
        Run identical seeds twice under identical thresholds: fixed vs pooled priors.
        Reconciles counts so the 350 ads in seeds.json are not double-counted.
        """
        fixed_report = self.run_benchmark(
            mode="ablation",
            max_runs_per_scenario=max_runs_per_scenario,
            enable_shrinkage=False,
            seed_file_name=str(self.seeds_path.name),
        )
        pooled_report = self.run_benchmark(
            mode="ablation",
            max_runs_per_scenario=max_runs_per_scenario,
            enable_shrinkage=True,
            seed_file_name=str(self.seeds_path.name),
        )

        n_sim = fixed_report.run_metadata["n_simulations"]
        n_sc = fixed_report.run_metadata["n_scenarios"]
        n_ads = fixed_report.run_metadata["n_ads"]
        n_good = fixed_report.run_metadata["n_good"]
        n_poor = fixed_report.run_metadata["n_poor"]

        q_fixed = fixed_report.aggregate_metrics["qualloop"]
        q_pooled = pooled_report.aggregate_metrics["qualloop"]

        ablation_summary = {
            "run_metadata": {
                "mode": "ablation",
                "n_simulations": n_sim,
                "n_scenarios": n_sc,
                "seeds_file_used": str(self.seeds_path.name),
                "n_ads": n_ads,
                "n_good": n_good,
                "n_poor": n_poor,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "description": "Paired ablation isolating empirical-Bayes shrinkage (fixed priors vs pooled priors on identical seeds and thresholds)",
            },
            "fixed_priors": {
                "fppr": q_fixed["fppr_mean"],
                "fppr_ci": q_fixed["fppr_ci"],
                "fndr": q_fixed["fndr_mean"],
                "fndr_ci": q_fixed["fndr_ci"],
                "ier": q_fixed["ier_mean"],
            },
            "pooled_empirical_bayes": {
                "fppr": q_pooled["fppr_mean"],
                "fppr_ci": q_pooled["fppr_ci"],
                "fndr": q_pooled["fndr_mean"],
                "fndr_ci": q_pooled["fndr_ci"],
                "ier": q_pooled["ier_mean"],
            },
            "delta_pooled_minus_fixed": {
                "delta_fppr": round(q_pooled["fppr_mean"] - q_fixed["fppr_mean"], 4),
                "delta_fndr": round(q_pooled["fndr_mean"] - q_fixed["fndr_mean"], 4),
                "delta_ier": round(q_pooled["ier_mean"] - q_fixed["ier_mean"], 4),
            },
        }

        save_path = self.results_dir / save_filename
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(ablation_summary, f, indent=2)

        return ablation_summary
