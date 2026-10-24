"""
Sequential Closed-Loop Benchmark Simulation.

In this experiment, policies act sequentially at checkpoints (days 3, 7, 14, 21).
When an ad is paused at checkpoint t_cp:
1. It permanently stops accruing spend from day t_cp onward:
   final_spend = full_spend * (t_cp / horizon).
2. It permanently stops generating leads: any leads scheduled on or after day t_cp
   are never generated.
3. Leads created before t_cp complete their call attempts and qualification.

The Oracle:
- Omniscient ground-truth agent that pauses all truly poor ads at Day 0 (t = 0).
- Spend on truly poor ads under Oracle is exactly $0.00.
- Truly good ads run for the full duration, accruing full spend and full qualified leads.
- Oracle cumulative spend = sum of good ads' spend (strictly differs from policies).

Policies evaluated:
- oracle: ground-truth optimal reference
- qualloop: uncertainty-aware sequential policy
- baseline_b: naive qualification heuristic (unreached/pending leads counted as failures)
- baseline_a: top-of-funnel optimizer (optimizes on CPL and CTR only, ignores CRM qualification)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

backend_root = str(Path(__file__).resolve().parent.parent)
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from benchmark.baseline import BaselineDecision, BaselinePolicy, BaselineCPolicy
from decision_engine.engine import DecisionPolicy, evaluate_campaign, evaluate
from domain.enums import DecisionAction, QualificationResult
from domain.models import Advertisement, CallAttempt, Lead, QualificationOutcome
from estimator.estimator import EstimatorConfig, compute_campaign_estimates
from simulator.engine import SimulationResult, run_simulation
from simulator.scenarios import ScenarioConfig, get_scenario


def is_pause(action: str | DecisionAction) -> bool:
    val = action.value if isinstance(action, DecisionAction) else str(action)
    return val in ("pause_ad", "consider_pause") or "pause" in val.lower()


@dataclass
class AdSequentialResult:
    ad_id: str
    scenario_name: str
    seed: int
    creative_id: str
    is_good: bool
    is_poor: bool
    full_spend: float
    full_qualified_leads: int
    intent_label: str = "good"
    economic_label: str = "good"
    true_cpql: float = 0.0
    is_good_economic: bool = True
    is_poor_economic: bool = False

    # Outcomes under each policy
    paused_day: dict[str, Optional[int]] = field(default_factory=dict)
    spend_incurred: dict[str, float] = field(default_factory=dict)
    qualified_leads_realized: dict[str, float] = field(default_factory=dict)
    qualified_leads_forgone: dict[str, float] = field(default_factory=dict)


@dataclass
class PolicySummary:
    policy_name: str
    budget_mode: str
    total_budget: float
    cumulative_spend: float
    qualified_leads: float
    ql_per_rupee: float
    cpql: float
    efficiency_vs_oracle: float
    spend_on_poor_ads: float
    qualified_leads_forgone_from_good_ads: float
    poor_ads_paused_by_checkpoint: dict[str, int]
    poor_ads_missed: int
    poor_ads_mean_days_to_pause: Optional[float]
    good_ads_false_paused: int
    good_ads_false_pause_rate: float


class SequentialClosedLoopRunner:
    """Executes closed-loop sequential benchmark at checkpoints (days 3, 7, 14, 21)."""

    def __init__(
        self,
        seeds_path: Optional[Path] = None,
        results_dir: Optional[Path] = None,
        checkpoints: tuple[int, ...] = (3, 7, 14, 21),
        decision_policy: Optional[DecisionPolicy] = None,
        estimator_config: Optional[EstimatorConfig] = None,
    ):
        base_dir = Path(__file__).resolve().parent
        self.seeds_path = seeds_path or (base_dir / "seeds.json")
        self.results_dir = results_dir or (base_dir / "results")
        self.checkpoints = sorted(list(checkpoints))
        self.decision_policy = decision_policy or DecisionPolicy()
        self.estimator_config = estimator_config or EstimatorConfig()
        self.baseline_b_policy = BaselinePolicy(pause_threshold=0.10)
        self.baseline_c_policy = BaselineCPolicy(
            pause_threshold=0.15,
            min_contacts=12,
            qualification_maturity_days=7.0,
        )

    def load_seeds(self) -> dict[str, list[int]]:
        with open(self.seeds_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_baseline_a(
        self,
        ad: Advertisement,
        accrued_spend: float,
        visible_leads: list[Lead],
        day: int,
        target_cpl: float = 75.0,
        min_ctr: float = 0.012,
    ) -> bool:
        """
        Baseline A: Top-of-funnel CPL and CTR optimizer.
        Ignores CRM qualification entirely.
        Pauses if CPL > target_cpl (with min 3 leads) or CTR < min_ctr.
        """
        n_leads = len(visible_leads)
        ctr = ad.clicks / max(ad.impressions, 1)
        if ctr < min_ctr and day >= 7:
            return True
        if n_leads >= 5:
            cpl = accrued_spend / max(n_leads, 1)
            if cpl > target_cpl * 1.5:  # significantly over CPL target
                return True
        return False

    def run_simulation_closed_loop(
        self,
        seeds: Optional[dict[str, list[int]]] = None,
        max_runs_per_scenario: Optional[int] = None,
        budget_mode: str = "variable",
    ) -> list[AdSequentialResult]:
        scenario_seeds = seeds if seeds is not None else self.load_seeds()
        ad_results: list[AdSequentialResult] = []

        policies = ["oracle", "qualloop", "baseline_b", "baseline_a", "baseline_c"]

        for scenario_name, seed_list in scenario_seeds.items():
            if max_runs_per_scenario is not None:
                seed_list = seed_list[:max_runs_per_scenario]

            for seed in seed_list:
                cfg = get_scenario(scenario_name, seed=seed)
                sim = run_simulation(cfg)
                epoch = sim.run.started_at
                horizon = cfg.time_horizon_days

                # Map ground truth
                gt_by_ad = {g.advertisement_id: g for g in sim.ground_truth}
                ad_set_map = {aset.id: aset for aset in sim.ad_sets}
                ad_to_camp = {ad.id: ad_set_map[ad.ad_set_id].campaign_id for ad in sim.advertisements}
                camp_to_ads: dict[str, list[Advertisement]] = {}
                for ad in sim.advertisements:
                    camp_to_ads.setdefault(ad_to_camp[ad.id], []).append(ad)

                # Pre-calculate lead creation times and qualification outcomes
                leads_by_ad = {ad.id: [] for ad in sim.advertisements}
                for l in sim.leads:
                    if l.advertisement_id in leads_by_ad:
                        leads_by_ad[l.advertisement_id].append(l)

                calls_by_ad = {ad.id: [] for ad in sim.advertisements}
                lead_to_ad = {l.id: l.advertisement_id for l in sim.leads}
                for ca in sim.call_attempts:
                    ad_id = lead_to_ad.get(ca.lead_id)
                    if ad_id and ad_id in calls_by_ad:
                        calls_by_ad[ad_id].append(ca)

                quals_by_ad = {ad.id: [] for ad in sim.advertisements}
                qual_lead_ids_by_ad = {ad.id: set() for ad in sim.advertisements}
                for qo in sim.qualification_outcomes:
                    ad_id = lead_to_ad.get(qo.lead_id)
                    if ad_id and ad_id in quals_by_ad:
                        quals_by_ad[ad_id].append(qo)
                        if qo.result == QualificationResult.QUALIFIED:
                            qual_lead_ids_by_ad[ad_id].add(qo.lead_id)

                # Initialize tracking per policy
                paused_day = {p: {ad.id: None for ad in sim.advertisements} for p in policies}

                # 1. Oracle pauses truly poor ads at Day 0
                for ad in sim.advertisements:
                    gt = gt_by_ad[ad.id]
                    if gt.label == "bad":
                        paused_day["oracle"][ad.id] = 0

                # 2. Sequential simulation across checkpoints
                for cp_day in self.checkpoints:
                    t_cp = epoch + timedelta(days=cp_day)

                    # Visible data up to checkpoint
                    visible_leads_by_ad = {
                        ad.id: [l for l in leads_by_ad[ad.id] if l.created_at <= t_cp]
                        for ad in sim.advertisements
                    }
                    visible_calls_by_ad = {
                        ad.id: [c for c in calls_by_ad[ad.id] if c.attempted_at <= t_cp]
                        for ad in sim.advertisements
                    }
                    visible_quals_by_ad = {
                        ad.id: [q for q in quals_by_ad[ad.id] if q.resolved_at <= t_cp]
                        for ad in sim.advertisements
                    }

                    # Compute spend accrued up to cp_day
                    accrued_spends = {
                        ad.id: round(ad.spend * (cp_day / horizon), 2)
                        for ad in sim.advertisements
                    }

                    # Evaluate QualLoop
                    active_ads_ql = [ad for ad in sim.advertisements if paused_day["qualloop"][ad.id] is None]
                    if active_ads_ql:
                        ads_data_ql = [
                            (
                                ad,
                                visible_leads_by_ad[ad.id],
                                visible_calls_by_ad[ad.id],
                                visible_quals_by_ad[ad.id],
                            )
                            for ad in active_ads_ql
                        ]
                        snapshots_ql = compute_campaign_estimates(
                            ads_data=ads_data_ql,
                            observation_time=t_cp,
                            config=self.estimator_config,
                            seed=seed,
                        )
                        ql_decisions = evaluate_campaign(
                            snapshots=snapshots_ql,
                            ad_spends={ad.id: accrued_spends[ad.id] for ad in active_ads_ql},
                            policy=self.decision_policy,
                        )
                        for dec in ql_decisions:
                            if is_pause(dec.action):
                                paused_day["qualloop"][dec.advertisement_id] = cp_day

                    # Evaluate Baseline B
                    for ad in sim.advertisements:
                        if paused_day["baseline_b"][ad.id] is None:
                            b_dec = self.baseline_b_policy.evaluate(
                                advertisement=ad,
                                leads=visible_leads_by_ad[ad.id],
                                call_attempts=visible_calls_by_ad[ad.id],
                                qualification_outcomes=visible_quals_by_ad[ad.id],
                            )
                            if is_pause(b_dec.action):
                                paused_day["baseline_b"][ad.id] = cp_day

                    # Evaluate Baseline A
                    for ad in sim.advertisements:
                        if paused_day["baseline_a"][ad.id] is None:
                            should_pause = self.evaluate_baseline_a(
                                ad=ad,
                                accrued_spend=accrued_spends[ad.id],
                                visible_leads=visible_leads_by_ad[ad.id],
                                day=cp_day,
                            )
                            if should_pause:
                                paused_day["baseline_a"][ad.id] = cp_day

                    # Evaluate Baseline C
                    for ad in sim.advertisements:
                        if paused_day["baseline_c"][ad.id] is None:
                            c_dec = self.baseline_c_policy.evaluate(
                                advertisement=ad,
                                leads=visible_leads_by_ad[ad.id],
                                call_attempts=visible_calls_by_ad[ad.id],
                                qualification_outcomes=visible_quals_by_ad[ad.id],
                                observation_time=t_cp,
                            )
                            if is_pause(c_dec.action):
                                paused_day["baseline_c"][ad.id] = cp_day

                # 3. Compute final closed-loop accounting for each ad under each policy
                run_ad_results = []
                for ad in sim.advertisements:
                    gt = gt_by_ad[ad.id]
                    is_good = gt.label == "good"
                    is_poor = gt.label == "bad"
                    all_ad_quals = qual_lead_ids_by_ad[ad.id]
                    full_ql_count = len(all_ad_quals)

                    # Ground truth expected true-rate CPQL based on underlying reachability and intent:
                    mean_intent = float(np.mean(gt.true_intent_by_day))
                    exp_ql = horizon * cfg.leads_per_day_per_ad * gt.true_reachability * mean_intent
                    true_rate_cpql = round(ad.spend / exp_ql, 2) if exp_ql > 0 else float("inf")
                    # Target CPQL: standard campaign ceiling is ₹500.0.
                    # All standard good ads have true-rate CPQL <= ₹433.
                    # high_cpql produces true-rate CPQL = ₹2,976.19 >> ₹500, making it good by intent (q=20% >= 15%)
                    # but unambiguously poor by unit economics.
                    target_cpql_ceiling = 500.0
                    is_good_economic = is_good and (true_rate_cpql <= target_cpql_ceiling)
                    is_poor_economic = not is_good_economic

                    res = AdSequentialResult(
                        ad_id=ad.id,
                        scenario_name=scenario_name,
                        seed=seed,
                        creative_id=ad.creative_id,
                        is_good=is_good,
                        is_poor=is_poor,
                        full_spend=ad.spend,
                        full_qualified_leads=full_ql_count,
                        intent_label="good" if is_good else "poor",
                        economic_label="good" if is_good_economic else "poor",
                        true_cpql=true_rate_cpql,
                        is_good_economic=is_good_economic,
                        is_poor_economic=is_poor_economic,
                    )
                    for p in policies:
                        res.paused_day[p] = paused_day[p][ad.id]
                    run_ad_results.append(res)

                if budget_mode == "fixed_redistributed":
                    # Fixed-total-budget variant: budget freed by paused ads is redistributed
                    # equally across remaining active ads in the same campaign.
                    intervals = [
                        (0, 3),
                        (3, 7),
                        (7, 14),
                        (14, 21),
                        (21, horizon),
                    ]
                    for p in policies:
                        for camp_id, camp_ads in camp_to_ads.items():
                            camp_tot_spend = sum(a.spend for a in camp_ads)
                            camp_daily = camp_tot_spend / horizon

                            for t_start, t_end in intervals:
                                dt = t_end - t_start
                                int_budget = camp_daily * dt
                                active_in_int = [
                                    a for a in camp_ads
                                    if paused_day[p][a.id] is None or paused_day[p][a.id] > t_start
                                ]
                                n_act = len(active_in_int)

                                for a in camp_ads:
                                    ad_res = next(r for r in run_ad_results if r.ad_id == a.id)
                                    base_int_spend = a.spend * (dt / horizon)

                                    int_leads = [
                                        l for l in leads_by_ad[a.id]
                                        if t_start <= (l.created_at - epoch).total_seconds() / 86400.0 < t_end
                                    ]
                                    int_base_quals = sum(1 for l in int_leads if l.id in qual_lead_ids_by_ad[a.id])

                                    if a in active_in_int:
                                        int_spend = int_budget / n_act
                                        mult = int_spend / base_int_spend if base_int_spend > 0 else 1.0
                                        int_quals = int_base_quals * mult
                                    else:
                                        int_spend = 0.0
                                        int_quals = 0.0

                                    ad_res.spend_incurred[p] = round(ad_res.spend_incurred.get(p, 0.0) + int_spend, 2)
                                    ad_res.qualified_leads_realized[p] = round(ad_res.qualified_leads_realized.get(p, 0.0) + int_quals, 4)

                        for ad_res in run_ad_results:
                            if ad_res.is_good and ad_res.paused_day[p] is not None:
                                ad_res.qualified_leads_forgone[p] = round(
                                    max(0.0, ad_res.full_qualified_leads - ad_res.qualified_leads_realized[p]), 4
                                )
                            else:
                                ad_res.qualified_leads_forgone[p] = 0.0
                else:
                    # Standard variable-spend closed loop
                    for p in policies:
                        for ad_res in run_ad_results:
                            ad = next(a for a in sim.advertisements if a.id == ad_res.ad_id)
                            p_day = ad_res.paused_day[p]
                            all_ad_quals = qual_lead_ids_by_ad[ad.id]
                            full_ql_count = len(all_ad_quals)

                            if p_day is not None:
                                spend = round(ad.spend * (p_day / horizon), 2)
                                t_p = epoch + timedelta(days=p_day)
                                pre_pause_quals = sum(
                                    1 for l in leads_by_ad[ad.id]
                                    if l.created_at < t_p and l.id in all_ad_quals
                                )
                                post_pause_quals = full_ql_count - pre_pause_quals
                                ad_res.spend_incurred[p] = spend
                                ad_res.qualified_leads_realized[p] = float(pre_pause_quals)
                                ad_res.qualified_leads_forgone[p] = float(post_pause_quals if ad_res.is_good else 0)
                            else:
                                ad_res.spend_incurred[p] = ad.spend
                                ad_res.qualified_leads_realized[p] = float(full_ql_count)
                                ad_res.qualified_leads_forgone[p] = 0.0

                ad_results.extend(run_ad_results)

        return ad_results

    def summarize_policy(
        self,
        policy_name: str,
        results: list[AdSequentialResult],
        oracle_ql_per_rupee: float,
        budget_mode: str = "variable",
    ) -> PolicySummary:
        total_budget = sum(r.full_spend for r in results)
        total_spend = sum(r.spend_incurred[policy_name] for r in results)
        total_ql = sum(r.qualified_leads_realized[policy_name] for r in results)
        ql_per_rupee = total_ql / total_spend if total_spend > 0 else 0.0

        if budget_mode == "fixed_redistributed":
            cpql = total_budget / total_ql if total_ql > 0 else float("inf")
        else:
            cpql = total_spend / total_ql if total_ql > 0 else float("inf")

        poor_ads = [r for r in results if r.is_poor]
        good_ads = [r for r in results if r.is_good]

        spend_poor = sum(r.spend_incurred[policy_name] for r in poor_ads)
        lost_good_ql = sum(r.qualified_leads_forgone[policy_name] for r in good_ads)

        # Pause day distribution for poor ads
        p_dist = {f"day_{d}": 0 for d in self.checkpoints}
        if "day_0" not in p_dist:
            p_dist["day_0"] = 0
        missed_count = 0
        days_list = []

        for r in poor_ads:
            d = r.paused_day[policy_name]
            if d is None:
                missed_count += 1
            else:
                p_dist[f"day_{d}"] = p_dist.get(f"day_{d}", 0) + 1
                days_list.append(d)

        # Good ad false pause count
        good_fp_count = sum(1 for r in good_ads if r.paused_day[policy_name] is not None)
        good_fp_rate = good_fp_count / len(good_ads) if good_ads else 0.0

        return PolicySummary(
            policy_name=policy_name,
            budget_mode=budget_mode,
            total_budget=round(total_budget, 2),
            cumulative_spend=round(total_spend, 2),
            qualified_leads=round(total_ql, 2),
            ql_per_rupee=round(ql_per_rupee, 6),
            cpql=round(cpql, 2),
            efficiency_vs_oracle=round(ql_per_rupee / oracle_ql_per_rupee, 4) if oracle_ql_per_rupee > 0 else 0.0,
            spend_on_poor_ads=round(spend_poor, 2),
            qualified_leads_forgone_from_good_ads=round(lost_good_ql, 2),
            poor_ads_paused_by_checkpoint=p_dist,
            poor_ads_missed=missed_count,
            poor_ads_mean_days_to_pause=float(np.mean(days_list)) if days_list else None,
            good_ads_false_paused=good_fp_count,
            good_ads_false_pause_rate=round(good_fp_rate, 4),
        )

    def run_benchmark(
        self,
        seeds: Optional[dict[str, list[int]]] = None,
        seed_file_name: Optional[str] = None,
        max_runs_per_scenario: Optional[int] = None,
        save_filename: str = "sequential_closed_loop.json",
        budget_mode: str = "variable",
    ) -> dict[str, Any]:
        results = self.run_simulation_closed_loop(
            seeds=seeds,
            max_runs_per_scenario=max_runs_per_scenario,
            budget_mode=budget_mode,
        )

        n_ads = len(results)
        n_good = sum(1 for r in results if r.is_good)
        n_poor = sum(1 for r in results if r.is_poor)
        scenarios_seen = sorted(list({r.scenario_name for r in results}))
        sims_seen = len({(r.scenario_name, r.seed) for r in results})

        # Calculate Oracle base metrics
        oracle_spend = sum(r.spend_incurred["oracle"] for r in results)
        oracle_ql = sum(r.qualified_leads_realized["oracle"] for r in results)
        oracle_ql_per_rupee = oracle_ql / oracle_spend if oracle_spend > 0 else 0.0

        summaries = {}
        for p in ["oracle", "qualloop", "baseline_b", "baseline_a", "baseline_c"]:
            summaries[p] = asdict(self.summarize_policy(p, results, oracle_ql_per_rupee, budget_mode=budget_mode))

        output = {
            "run_metadata": {
                "experiment": "sequential_closed_loop_simulation" if budget_mode == "variable" else f"sequential_closed_loop_simulation_{budget_mode}",
                "budget_mode": budget_mode,
                "checkpoints": self.checkpoints,
                "n_simulations": sims_seen,
                "n_scenarios": len(scenarios_seen),
                "seeds_file_used": seed_file_name or str(self.seeds_path.name),
                "n_ads": n_ads,
                "n_good": n_good,
                "n_poor": n_poor,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "closed_loop_definition": (
                    "A paused ad permanently stops accruing spend and leads from that checkpoint day forward. "
                    "In fixed_redistributed mode, freed budget is redistributed equally across remaining active ads in the campaign."
                ),
                "oracle_definition": (
                    "Omniscient benchmark agent that pauses all truly poor ads at Day 0 (t = 0), spending $0.00 on poor ads, "
                    "while running all truly good ads to completion."
                ),
            },
            "policies": summaries,
        }

        self.results_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.results_dir / save_filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)

        return output


if __name__ == "__main__":
    runner = SequentialClosedLoopRunner()
    print("Running Sequential Closed-Loop Benchmark (Variable Spend, 200 seeds)...")
    res_var = runner.run_benchmark(save_filename="sequential_closed_loop.json", budget_mode="variable")
    print("Running Sequential Fixed-Budget Benchmark (Redistributed Spend, 200 seeds)...")
    res_fixed = runner.run_benchmark(save_filename="sequential_fixed_budget.json", budget_mode="fixed_redistributed")
    print("Completed. Fixed Budget Headline Metrics:")
    for p, s in res_fixed["policies"].items():
        print(f"  {p:12s}: QL={s['qualified_leads']:8.2f}, CPQL=Rs {s['cpql']:6.2f}, Spend=Rs {s['cumulative_spend']:10.2f}")

