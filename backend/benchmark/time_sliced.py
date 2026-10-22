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
from domain.enums import DecisionAction
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


@dataclass
class TimeSlicedBenchmarkSummary:
    """Summary of time-sliced evaluation across all scenarios and seeds."""

    checkpoints: list[int]
    n_simulations: int
    n_poor_ads: int
    n_good_ads: int

    # Poor ad trajectory distributions
    qualloop_distribution: dict[str, int]  # e.g. {"day_3": 5, "day_7": 20, "missed": 10}
    baseline_distribution: dict[str, int]

    qualloop_missed_count: int
    qualloop_missed_rate: float
    baseline_missed_count: int
    baseline_missed_rate: float

    qualloop_mean_days_to_correct: Optional[float]
    baseline_mean_days_to_correct: Optional[float]

    # Good ad false pause counts by checkpoint
    qualloop_fp_by_day: dict[int, int]
    baseline_fp_by_day: dict[int, int]

    trajectories: list[AdTimeSliceTrajectory] = field(default_factory=list)


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

                # Finalize trajectories for this simulation
                for traj in sim_trajectories.values():
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

        return TimeSlicedBenchmarkSummary(
            checkpoints=self.checkpoints,
            n_simulations=n_simulations,
            n_poor_ads=n_poor,
            n_good_ads=n_good,
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
            trajectories=trajectories,
        )
