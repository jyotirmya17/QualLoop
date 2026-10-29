"""
Scenario dataset generators for shadow evaluation and benchmark suites.
"""

from __future__ import annotations

from typing import Dict, Any, List
import numpy as np

from backend.simulator.engine import run_simulation
from backend.simulator.scenarios import AdConfig, ScenarioConfig, get_scenario, SCENARIO_REGISTRY


def generate_continuous_scenario(seed: int, n_ads: int = 3) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        true_intent = round(float(rng.uniform(0.05, 0.25)), 4)
        true_reach = round(float(rng.uniform(0.40, 0.70)), 4)
        clicks = int(rng.integers(1200, 3500))
        spend = float(rng.choice([3000.0, 5000.0, 7500.0]))
        ads.append(
            AdConfig(
                creative_id=f"cr-cont-{seed}-{i}",
                spend=spend,
                impressions=100000,
                clicks=clicks,
                true_reachability=true_reach,
                true_intent=true_intent,
                fatigue_enabled=False,
                label="unlabelled",
            )
        )
    return ScenarioConfig(
        seed=seed,
        scenario_name="continuous_intent",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[ads],
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
        leads_per_day_per_ad=5.0,
    )


def generate_bimodal_scenario(seed: int, n_ads: int = 3) -> ScenarioConfig:
    rng = np.random.default_rng(seed)
    ads = []
    for i in range(n_ads):
        is_high = rng.random() < 0.40
        if is_high:
            true_intent = round(float(rng.uniform(0.20, 0.32)), 4)
        else:
            true_intent = round(float(rng.uniform(0.03, 0.06)), 4)
        true_reach = round(float(rng.uniform(0.50, 0.70)), 4)
        spend = float(rng.choice([4000.0, 5000.0, 6000.0]))
        ads.append(
            AdConfig(
                creative_id=f"cr-bimodal-{seed}-{i}",
                spend=spend,
                impressions=100000,
                clicks=2500,
                true_reachability=true_reach,
                true_intent=true_intent,
                fatigue_enabled=False,
                label="unlabelled",
            )
        )
    return ScenarioConfig(
        seed=seed,
        scenario_name="bimodal_intent_synthetic",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[ads],
        contact_maturity_days=3.0,
        qualification_maturity_days=7.0,
        leads_per_day_per_ad=5.0,
    )


def build_dataset() -> List[Dict[str, Any]]:
    simulations = []
    for seed in range(22000, 22050):
        cfg = generate_continuous_scenario(seed=seed, n_ads=3)
        sim = run_simulation(cfg)
        simulations.append({
            "family": "continuous",
            "scenario_name": "continuous_intent",
            "seed": seed,
            "cfg": cfg,
            "sim": sim,
        })

    for seed in range(24000, 24050):
        cfg = generate_bimodal_scenario(seed=seed, n_ads=3)
        sim = run_simulation(cfg)
        simulations.append({
            "family": "bimodal_synthetic",
            "scenario_name": "bimodal_intent_synthetic",
            "seed": seed,
            "cfg": cfg,
            "sim": sim,
        })

    for p_name in sorted(list(SCENARIO_REGISTRY.keys())):
        for s_idx in range(1, 11):
            seed = 26000 + s_idx
            cfg = get_scenario(p_name, seed=seed)
            sim = run_simulation(cfg)
            simulations.append({
                "family": "preset",
                "scenario_name": p_name,
                "seed": seed,
                "cfg": cfg,
                "sim": sim,
            })

    return simulations
