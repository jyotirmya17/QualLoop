"""
Time-sliced benchmark evaluation across checkpoints (days 3, 7, 14, 21).

ARCHITECTURE BOUNDARY:
This module accesses SimulationResult.ground_truth exclusively to evaluate
when QualLoop and the baseline policies reach the correct decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from benchmark.baseline import BaselineDecision, BaselinePolicy
from decision_engine.engine import DecisionPolicy, evaluate_campaign
from domain.enums import DecisionAction, QualificationResult
from domain.models import Advertisement, CallAttempt, Lead, QualificationOutcome
from estimator.estimator import EstimatorConfig, compute_campaign_estimates
from simulator.engine import SimulationResult, run_simulation
from simulator.scenarios import ScenarioConfig, get_scenario


@dataclass
class AdTimeSliceTrajectory:
    """Tracking decision progression for a single advertisement over time."""

    ad_id: str
    scenario_name: str
    seed: int
    is_poor_ad: bool
    is_good_ad: bool
    gt_label: str

    # Decision at each checkpoint (e.g. {3: "continue_monitoring", 7: "pause_ad", ...})
    qualloop_actions_by_day: dict[int, str] = field(default_factory=dict)
    baseline_actions_by_day: dict[int, str] = field(default_factory=dict)

    # First day when pause occurred (None if never paused)
    qualloop_paused_day: Optional[int] = None
    baseline_paused_day: Optional[int] = None

    # Correct decision tracking for poor ads (None if good ad)
    qualloop_missed: Optional[bool] = None
    baseline_missed: Optional[bool] = None
    qualloop_days_to_correct: Optional[int] = None
    baseline_days_to_correct: Optional[int] = None

    # Spend and conversion accounting
    full_ad_spend: float = 0.0
    total_qualified_leads: int = 0
    qualloop_spend_incurred: float = 0.0
    baseline_spend_incurred: float = 0.0
    qualloop_lost_qualified_leads: int = 0
    baseline_lost_qualified_leads: int = 0


@dataclass
class TimeSlicedBenchmarkSummary:
    """Summary of time-sliced evaluation across all scenarios and seeds."""

    checkpoints: list[int]
    n_simulations: int
    n_poor_ads: int
    n_good_ads: int
    n_scenarios: int = 9
    seeds_file_used: str = "seeds.json"
    n_ads: int = 0

    # Poor ad trajectory distributions
    qualloop_distribution: dict[str, int] = field(default_factory=dict)
    baseline_distribution: dict[str, int] = field(default_factory=dict)

    qualloop_missed_count: int = 0
    qualloop_missed_rate: float = 0.0
    baseline_missed_count: int = 0
    baseline_missed_rate: float = 0.0

    qualloop_mean_days_to_correct: Optional[float] = None
    baseline_mean_days_to_correct: Optional[float] = None

    # Good ad false pause counts by checkpoint
    qualloop_fp_by_day: dict[int, int] = field(default_factory=dict)
    baseline_fp_by_day: dict[int, int] = field(default_factory=dict)

    # Spend-weighted metrics
    qualloop_poor_ad_spend_before_pause: float = 0.0
    baseline_poor_ad_spend_before_pause: float = 0.0
    qualloop_qualified_leads_lost_from_good_ads: int = 0
    baseline_qualified_leads_lost_from_good_ads: int = 0
    oracle_spend: float = 0.0
    oracle_qualified_leads: int = 0
    oracle_ql_per_rupee: float = 0.0
    qualloop_ql_per_rupee: float = 0.0
    baseline_ql_per_rupee: float = 0.0
    qualloop_vs_oracle_efficiency: float = 0.0
    baseline_vs_oracle_efficiency: float = 0.0

    trajectories: list[AdTimeSliceTrajectory] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_metadata": {
                "mode": "time_sliced",
                "n_simulations": self.n_simulations,
                "n_scenarios": self.n_scenarios,
                "seeds_file_used": self.seeds_file_used,
                "n_ads": self.n_ads or (self.n_poor_ads + self.n_good_ads),
                "n_good": self.n_good_ads,
                "n_poor": self.n_poor_ads,
                "checkpoints": self.checkpoints,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            },
            "metrics": {
                "qualloop_distribution": self.qualloop_distribution,
                "baseline_distribution": self.baseline_distribution,
                "qualloop_missed_count": self.qualloop_missed_count,
                "qualloop_missed_rate": self.qualloop_missed_rate,
                "baseline_missed_count": self.baseline_missed_count,
                "baseline_missed_rate": self.baseline_missed_rate,
                "qualloop_mean_days_to_correct": self.qualloop_mean_days_to_correct,
                "baseline_mean_days_to_correct": self.baseline_mean_days_to_correct,
                "qualloop_fp_by_day": self.qualloop_fp_by_day,
                "baseline_fp_by_day": self.baseline_fp_by_day,
                "qualloop_poor_ad_spend_before_pause": self.qualloop_poor_ad_spend_before_pause,
                "baseline_poor_ad_spend_before_pause": self.baseline_poor_ad_spend_before_pause,
                "qualloop_qualified_leads_lost_from_good_ads": self.qualloop_qualified_leads_lost_from_good_ads,
                "baseline_qualified_leads_lost_from_good_ads": self.baseline_qualified_leads_lost_from_good_ads,
                "oracle_spend": self.oracle_spend,
                "oracle_qualified_leads": self.oracle_qualified_leads,
                "oracle_ql_per_rupee": self.oracle_ql_per_rupee,
                "qualloop_ql_per_rupee": self.qualloop_ql_per_rupee,
                "baseline_ql_per_rupee": self.baseline_ql_per_rupee,
                "qualloop_vs_oracle_efficiency": self.qualloop_vs_oracle_efficiency,
                "baseline_vs_oracle_efficiency": self.baseline_vs_oracle_efficiency,
            },
        }

    def save_results(self, output_dir: Optional[Path] = None, filename: str = "time_sliced_benchmark.json") -> Path:
        base_dir = output_dir or (Path(__file__).resolve().parent / "results")
        base_dir.mkdir(parents=True, exist_ok=True)
        out_path = base_dir / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return out_path


def is_pause_action(action: str | DecisionAction) -> bool:
    val = action.value if isinstance(action, DecisionAction) else str(action)
    return val in ("pause_ad", "consider_pause") or "pause" in val.lower()


class TimeSlicedBenchmarkRunner:
    """Evaluates policies at checkpoints (days 3, 7, 14, 21)."""

    def __init__(
        self,
        seeds_path: Optional[Path] = None,
        estimator_config: Optional[EstimatorConfig] = None,
        decision_policy: Optional[DecisionPolicy] = None,
        baseline_policy: Optional[BaselinePolicy] = None,
        checkpoints: tuple[int, ...] = (3, 7, 14, 21),
    ):
        base_dir = Path(__file__).resolve().parent
        self.seeds_path = seeds_path or (base_dir / "seeds.json")
        self.estimator_config = estimator_config or EstimatorConfig()
        self.decision_policy = decision_policy or DecisionPolicy()
        self.baseline_policy = baseline_policy or BaselinePolicy()
        self.checkpoints = list(checkpoints)

    def load_seeds(self) -> dict[str, list[int]]:
        with open(self.seeds_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def run(
        self,
        max_runs_per_scenario: Optional[int] = None,
        enable_shrinkage: bool = True,
    ) -> TimeSlicedBenchmarkSummary:
        scenario_seeds = self.load_seeds()
        trajectories: list[AdTimeSliceTrajectory] = []
        n_simulations = 0

        final_checkpoint = max(self.checkpoints)

        for scenario_name, seeds in scenario_seeds.items():
            if max_runs_per_scenario is not None:
                seeds = seeds[:max_runs_per_scenario]

            for seed in seeds:
                n_simulations += 1
                cfg = get_scenario(scenario_name, seed=seed)
                sim: SimulationResult = run_simulation(cfg)
                epoch = sim.run.started_at
                horizon = cfg.time_horizon_days

                # Initialize trajectory tracking per ad
                sim_trajectories = {}
                for ad in sim.advertisements:
                    gt = next((g for g in sim.ground_truth if g.advertisement_id == ad.id), None)
                    label = gt.label if gt else "unlabelled"
                    is_poor = label == "bad"
                    is_good = label == "good"
                    sim_trajectories[ad.id] = AdTimeSliceTrajectory(
                        ad_id=ad.id,
                        scenario_name=scenario_name,
                        seed=seed,
                        is_poor_ad=is_poor,
                        is_good_ad=is_good,
                        gt_label=label,
                    )

                # Evaluate at each checkpoint chronologically
                for cp_day in sorted(self.checkpoints):
                    t_cp = epoch + timedelta(days=cp_day)
                    cp_fraction = min(1.0, cp_day / horizon)

                    # Visible slices up to checkpoint
                    visible_leads = [l for l in sim.leads if l.created_at <= t_cp]
                    visible_calls = [c for c in sim.call_attempts if c.attempted_at <= t_cp]
                    visible_quals = [q for q in sim.qualification_outcomes if q.resolved_at <= t_cp]

                    leads_by_ad = {ad.id: [] for ad in sim.advertisements}
                    for l in visible_leads:
                        if l.advertisement_id in leads_by_ad:
                            leads_by_ad[l.advertisement_id].append(l)

                    calls_by_ad = {ad.id: [] for ad in sim.advertisements}
                    leads_by_id = {l.id: l for l in visible_leads}
                    for ca in visible_calls:
                        l = leads_by_id.get(ca.lead_id)
                        if l and l.advertisement_id in calls_by_ad:
                            calls_by_ad[l.advertisement_id].append(ca)

                    quals_by_ad = {ad.id: [] for ad in sim.advertisements}
                    for qo in visible_quals:
                        l = leads_by_id.get(qo.lead_id)
                        if l and l.advertisement_id in quals_by_ad:
                            quals_by_ad[l.advertisement_id].append(qo)

                    # Create ads with prorated spend at checkpoint
                    cp_ads_data = []
                    cp_spends = {}
                    for ad in sim.advertisements:
                        prorated_spend = round(ad.spend * cp_fraction, 2)
                        prorated_ad = Advertisement(
                            id=ad.id,
                            ad_set_id=ad.ad_set_id,
                            creative_id=ad.creative_id,
                            spend=prorated_spend,
                            impressions=int(round(ad.impressions * cp_fraction)),
                            clicks=int(round(ad.clicks * cp_fraction)),
                        )
                        cp_spends[ad.id] = prorated_spend
                        cp_ads_data.append((
                            prorated_ad,
                            leads_by_ad[ad.id],
                            calls_by_ad[ad.id],
                            quals_by_ad[ad.id],
                        ))

                    # QualLoop estimates & decisions
                    ql_snapshots = compute_campaign_estimates(
                        ads_data=cp_ads_data,
                        observation_time=t_cp,
                        config=self.estimator_config,
                        seed=seed,
                        enable_shrinkage=enable_shrinkage,
                    )
                    ql_decisions = evaluate_campaign(
                        snapshots=ql_snapshots,
                        ad_spends=cp_spends,
                        policy=self.decision_policy,
                    )
                    ql_dec_by_ad = {d.advertisement_id: d for d in ql_decisions}

                    # Baseline decisions
                    for prorated_ad, l_list, c_list, q_list in cp_ads_data:
                        base_dec = self.baseline_policy.evaluate(
                            advertisement=prorated_ad,
                            leads=l_list,
                            call_attempts=c_list,
                            qualification_outcomes=q_list,
                        )
                        traj = sim_trajectories[prorated_ad.id]
                        ql_dec = ql_dec_by_ad.get(prorated_ad.id)
                        ql_act = ql_dec.action.value if ql_dec else "unknown"
                        base_act = base_dec.action.value

                        traj.qualloop_actions_by_day[cp_day] = ql_act
                        traj.baseline_actions_by_day[cp_day] = base_act

                        # Record first pause day
                        if traj.qualloop_paused_day is None and is_pause_action(ql_act):
                            traj.qualloop_paused_day = cp_day
                        if traj.baseline_paused_day is None and is_pause_action(base_act):
                            traj.baseline_paused_day = cp_day

                ad_map = {ad.id: ad for ad in sim.advertisements}
                lead_to_ad = {l.id: l.advertisement_id for l in sim.leads}
                ad_quals_map: dict[str, list[QualificationOutcome]] = {ad.id: [] for ad in sim.advertisements}
                for qo in sim.qualification_outcomes:
                    if qo.result == QualificationResult.QUALIFIED:
                        ad_id = lead_to_ad.get(qo.lead_id)
                        if ad_id and ad_id in ad_quals_map:
                            ad_quals_map[ad_id].append(qo)

                # Finalize trajectories for this simulation
                for traj in sim_trajectories.values():
                    ad = ad_map[traj.ad_id]
                    full_spend = ad.spend
                    quals = ad_quals_map.get(traj.ad_id, [])
                    traj.full_ad_spend = full_spend
                    traj.total_qualified_leads = len(quals)

                    # QualLoop spend & lost conversions
                    if traj.qualloop_paused_day is not None:
                        traj.qualloop_spend_incurred = round(full_spend * (traj.qualloop_paused_day / horizon), 2)
                        t_pause = epoch + timedelta(days=traj.qualloop_paused_day)
                        if traj.is_good_ad:
                            traj.qualloop_lost_qualified_leads = sum(1 for q in quals if q.resolved_at > t_pause)
                    else:
                        traj.qualloop_spend_incurred = full_spend
                        traj.qualloop_lost_qualified_leads = 0

                    # Baseline spend & lost conversions
                    if traj.baseline_paused_day is not None:
                        traj.baseline_spend_incurred = round(full_spend * (traj.baseline_paused_day / horizon), 2)
                        t_pause = epoch + timedelta(days=traj.baseline_paused_day)
                        if traj.is_good_ad:
                            traj.baseline_lost_qualified_leads = sum(1 for q in quals if q.resolved_at > t_pause)
                    else:
                        traj.baseline_spend_incurred = full_spend
                        traj.baseline_lost_qualified_leads = 0

                    if traj.is_poor_ad:
                        # QualLoop
                        if traj.qualloop_paused_day is not None:
                            traj.qualloop_missed = False
                            traj.qualloop_days_to_correct = traj.qualloop_paused_day
                        else:
                            traj.qualloop_missed = True
                            traj.qualloop_days_to_correct = None

                        # Baseline
                        if traj.baseline_paused_day is not None:
                            traj.baseline_missed = False
                            traj.baseline_days_to_correct = traj.baseline_paused_day
                        else:
                            traj.baseline_missed = True
                            traj.baseline_days_to_correct = None

                    trajectories.append(traj)

        # Aggregate metrics
        poor_trajs = [t for t in trajectories if t.is_poor_ad]
        good_trajs = [t for t in trajectories if t.is_good_ad]
        n_poor = len(poor_trajs)
        n_good = len(good_trajs)

        # Distribution for poor ads
        ql_dist = {f"day_{d}": 0 for d in self.checkpoints}
        ql_dist["missed"] = 0
        base_dist = {f"day_{d}": 0 for d in self.checkpoints}
        base_dist["missed"] = 0

        ql_days = []
        base_days = []

        for t in poor_trajs:
            if t.qualloop_missed:
                ql_dist["missed"] += 1
            else:
                ql_dist[f"day_{t.qualloop_days_to_correct}"] += 1
                ql_days.append(t.qualloop_days_to_correct)

            if t.baseline_missed:
                base_dist["missed"] += 1
            else:
                base_dist[f"day_{t.baseline_days_to_correct}"] += 1
                base_days.append(t.baseline_days_to_correct)

        # False pause counts on good ads by checkpoint
        ql_fp_by_day = {d: 0 for d in self.checkpoints}
        base_fp_by_day = {d: 0 for d in self.checkpoints}
        for t in good_trajs:
            if t.qualloop_paused_day is not None:
                ql_fp_by_day[t.qualloop_paused_day] += 1
            if t.baseline_paused_day is not None:
                base_fp_by_day[t.baseline_paused_day] += 1

        ql_missed_cnt = ql_dist["missed"]
        base_missed_cnt = base_dist["missed"]

        # Spend on truly poor ads before they were paused
        ql_poor_spend = round(sum(t.qualloop_spend_incurred for t in poor_trajs), 2)
        base_poor_spend = round(sum(t.baseline_spend_incurred for t in poor_trajs), 2)

        # Qualified leads lost from wrongly paused good ads
        ql_lost_good_quals = sum(t.qualloop_lost_qualified_leads for t in good_trajs)
        base_lost_good_quals = sum(t.baseline_lost_qualified_leads for t in good_trajs)

        # Oracle metrics: Oracle pauses all poor ads immediately and runs good ads fully
        oracle_spend = round(sum(t.full_ad_spend for t in good_trajs), 2)
        oracle_qual_leads = sum(t.total_qualified_leads for t in good_trajs)
        oracle_ql_per_rupee = oracle_qual_leads / oracle_spend if oracle_spend > 0 else 0.0

        # Total spend across all ads
        ql_total_spend = sum(t.qualloop_spend_incurred for t in trajectories)
        base_total_spend = sum(t.baseline_spend_incurred for t in trajectories)

        # Preserved qualified leads across all ads
        ql_preserved_quals = sum(t.total_qualified_leads - t.qualloop_lost_qualified_leads for t in trajectories)
        base_preserved_quals = sum(t.total_qualified_leads - t.baseline_lost_qualified_leads for t in trajectories)

        ql_per_rupee = ql_preserved_quals / ql_total_spend if ql_total_spend > 0 else 0.0
        base_per_rupee = base_preserved_quals / base_total_spend if base_total_spend > 0 else 0.0

        ql_eff = round(ql_per_rupee / oracle_ql_per_rupee, 4) if oracle_ql_per_rupee > 0 else 0.0
        base_eff = round(base_per_rupee / oracle_ql_per_rupee, 4) if oracle_ql_per_rupee > 0 else 0.0

        return TimeSlicedBenchmarkSummary(
            checkpoints=self.checkpoints,
            n_simulations=n_simulations,
            n_poor_ads=n_poor,
            n_good_ads=n_good,
            n_scenarios=len(set(t.scenario_name for t in trajectories)),
            seeds_file_used=str(self.seeds_path.name),
            n_ads=len(trajectories),
            qualloop_distribution=ql_dist,
            baseline_distribution=base_dist,
            qualloop_missed_count=ql_missed_cnt,
            qualloop_missed_rate=round(ql_missed_cnt / n_poor, 4) if n_poor > 0 else 0.0,
            baseline_missed_count=base_missed_cnt,
            baseline_missed_rate=round(base_missed_cnt / n_poor, 4) if n_poor > 0 else 0.0,
            qualloop_mean_days_to_correct=float(np.mean(ql_days)) if ql_days else None,
            baseline_mean_days_to_correct=float(np.mean(base_days)) if base_days else None,
            qualloop_fp_by_day=ql_fp_by_day,
            baseline_fp_by_day=base_fp_by_day,
            qualloop_poor_ad_spend_before_pause=ql_poor_spend,
            baseline_poor_ad_spend_before_pause=base_poor_spend,
            qualloop_qualified_leads_lost_from_good_ads=ql_lost_good_quals,
            baseline_qualified_leads_lost_from_good_ads=base_lost_good_quals,
            oracle_spend=oracle_spend,
            oracle_qualified_leads=oracle_qual_leads,
            oracle_ql_per_rupee=round(oracle_ql_per_rupee, 6),
            qualloop_ql_per_rupee=round(ql_per_rupee, 6),
            baseline_ql_per_rupee=round(base_per_rupee, 6),
            qualloop_vs_oracle_efficiency=ql_eff,
            baseline_vs_oracle_efficiency=base_eff,
            trajectories=trajectories,
        )
