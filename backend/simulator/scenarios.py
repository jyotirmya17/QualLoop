"""
Simulator configuration and scenario presets.

ScenarioConfig contains all parameters needed to generate a reproducible simulation.
Hidden ground truth (true_reachability, true_intent) is embedded here and is only
accessible to the benchmark module — never to the estimator or decision engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdConfig:
    """Configuration for a single advertisement within a simulation."""

    creative_id: str
    spend: float
    impressions: int
    clicks: int

    # Hidden ground truth — never accessed by estimator or decision engine
    true_reachability: float  # probability a lead is successfully contacted
    true_intent: float  # probability a contacted lead qualifies

    # Fatigue parameters
    fatigue_enabled: bool = False
    fatigue_start_day: int = 14  # day after which fatigue begins
    fatigue_rate: float = 0.05  # daily multiplicative decay on intent

    # Label for evaluation
    label: str = "unlabelled"  # "good", "bad", "mixed"


@dataclass
class ScenarioConfig:
    """
    Full configuration for a simulation run.

    seed: int — random seed for full reproducibility
    scenario_name: str — named preset
    time_horizon_days: int — how many simulated days the campaign runs
    n_campaigns: int — number of campaigns
    ads_per_campaign: list[AdConfig] — one list per campaign
    contact_maturity_days: float — leads must be this old for reachability analysis
    qualification_maturity_days: float — contacts must be this old for qual analysis
    leads_per_day_per_ad: float — mean daily lead rate per ad (Poisson)
    spend_is_uniform: bool — if True, spend is spread evenly; otherwise follows impressions
    """

    seed: int
    scenario_name: str
    time_horizon_days: int = 28
    n_campaigns: int = 1
    ads_per_campaign: list[list[AdConfig]] = field(default_factory=list)
    contact_maturity_days: float = 3.0
    qualification_maturity_days: float = 7.0
    leads_per_day_per_ad: float = 5.0
    # Call attempt timing: minutes after lead creation when first attempt happens
    first_call_attempt_mean_hours: float = 4.0
    # Max call attempts per lead
    max_call_attempts: int = 3
    # Hours between retry attempts
    retry_interval_hours: float = 24.0


# ---------------------------------------------------------------------------
# Named scenario presets
# ---------------------------------------------------------------------------

def healthy_campaign(seed: int) -> ScenarioConfig:
    """
    Balanced campaign: good reachability, reasonable qualification rates.
    All ads are genuinely good. Used as a sanity check.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="healthy_campaign",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_A",
                    spend=5000.0,
                    impressions=50000,
                    clicks=2000,
                    true_reachability=0.65,
                    true_intent=0.28,
                    label="good",
                ),
                AdConfig(
                    creative_id="creative_B",
                    spend=4500.0,
                    impressions=45000,
                    clicks=1800,
                    true_reachability=0.60,
                    true_intent=0.25,
                    label="good",
                ),
                AdConfig(
                    creative_id="creative_C",
                    spend=500.0,
                    impressions=5000,
                    clicks=200,
                    true_reachability=0.55,
                    true_intent=0.22,
                    label="good",
                ),
            ]
        ],
    )


def good_ad_low_reachability(seed: int) -> ScenarioConfig:
    """
    An ad with high buying intent but low reachability.
    Naive systems may incorrectly deprioritise this ad.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="good_ad_low_reachability",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_A_good_low_reach",
                    spend=6000.0,
                    impressions=60000,
                    clicks=2400,
                    true_reachability=0.18,  # low — hard to reach
                    true_intent=0.55,  # high — those reached often qualify
                    label="good",
                ),
                AdConfig(
                    creative_id="creative_B_avg",
                    spend=4000.0,
                    impressions=40000,
                    clicks=1600,
                    true_reachability=0.60,
                    true_intent=0.20,
                    label="good",
                ),
            ]
        ],
    )


def bad_ad_high_engagement(seed: int) -> ScenarioConfig:
    """
    An ad with many clicks and leads but very low qualification rate.
    The naive system may not catch this quickly due to raw volume.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="bad_ad_high_engagement",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_bad_hype",
                    spend=8000.0,
                    impressions=100000,
                    clicks=5000,
                    true_reachability=0.70,  # easy to reach
                    true_intent=0.03,  # almost no intent — bad leads
                    label="bad",
                ),
                AdConfig(
                    creative_id="creative_solid",
                    spend=2000.0,
                    impressions=20000,
                    clicks=800,
                    true_reachability=0.60,
                    true_intent=0.28,
                    label="good",
                ),
            ]
        ],
        leads_per_day_per_ad=8.0,  # higher volume for bad ad
    )


def small_sample_trap(seed: int) -> ScenarioConfig:
    """
    A new bad ad with very few leads but early accidental good performance.
    Tests whether the system correctly withholds a conclusion vs. the naive
    system that over-interprets early data.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="small_sample_trap",
        time_horizon_days=14,  # shorter window — few leads
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_new_bad",
                    spend=500.0,
                    impressions=5000,
                    clicks=200,
                    true_reachability=0.50,
                    true_intent=0.04,  # actually bad — but may not be visible yet
                    label="bad",
                ),
            ]
        ],
        leads_per_day_per_ad=1.5,  # few leads per day
    )


def delayed_conversion_trap(seed: int) -> ScenarioConfig:
    """
    Most qualification outcomes arrive after the naive analysis window.
    Tests correct maturity-window handling.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="delayed_conversion_trap",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_slow_qualify",
                    spend=5000.0,
                    impressions=50000,
                    clicks=2000,
                    true_reachability=0.55,
                    true_intent=0.30,
                    label="good",
                ),
            ]
        ],
        qualification_maturity_days=14.0,  # long qualification window
    )


def creative_fatigue(seed: int) -> ScenarioConfig:
    """
    Ad starts strong but intent degrades over time due to audience saturation.
    Tests anomaly detection on performance change.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="creative_fatigue",
        time_horizon_days=35,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_fatigue_ad",
                    spend=7000.0,
                    impressions=70000,
                    clicks=3000,
                    true_reachability=0.60,
                    true_intent=0.25,
                    fatigue_enabled=True,
                    fatigue_start_day=14,
                    fatigue_rate=0.06,  # intent decays 6% per day after day 14
                    label="good",  # good initially, becomes bad
                ),
            ]
        ],
    )


def mixed_portfolio(seed: int) -> ScenarioConfig:
    """
    Campaign with both good and bad ads — tests portfolio-level discrimination.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="mixed_portfolio",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_excellent",
                    spend=4000.0,
                    impressions=40000,
                    clicks=1600,
                    true_reachability=0.70,
                    true_intent=0.35,
                    label="good",
                ),
                AdConfig(
                    creative_id="creative_average",
                    spend=3000.0,
                    impressions=30000,
                    clicks=1200,
                    true_reachability=0.55,
                    true_intent=0.18,
                    label="good",
                ),
                AdConfig(
                    creative_id="creative_poor",
                    spend=3000.0,
                    impressions=30000,
                    clicks=1200,
                    true_reachability=0.65,
                    true_intent=0.04,
                    label="bad",
                ),
            ]
        ],
    )


def high_cpql(seed: int) -> ScenarioConfig:
    """
    Good qualification rate but very expensive spend per qualified lead.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="high_cpql",
        time_horizon_days=28,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_expensive_good",
                    spend=20000.0,  # very high spend
                    impressions=200000,
                    clicks=2000,
                    true_reachability=0.40,
                    true_intent=0.20,
                    label="good",  # good quality but expensive
                ),
            ]
        ],
        leads_per_day_per_ad=3.0,
    )


def sudden_deterioration(seed: int) -> ScenarioConfig:
    """
    Ad performs well then drops sharply at day 20.
    """
    return ScenarioConfig(
        seed=seed,
        scenario_name="sudden_deterioration",
        time_horizon_days=35,
        n_campaigns=1,
        ads_per_campaign=[
            [
                AdConfig(
                    creative_id="creative_sudden_drop",
                    spend=5000.0,
                    impressions=50000,
                    clicks=2000,
                    true_reachability=0.60,
                    true_intent=0.28,
                    fatigue_enabled=True,
                    fatigue_start_day=20,
                    fatigue_rate=0.35,  # very sharp drop
                    label="good",
                ),
            ]
        ],
    )


# Registry of all preset factory functions
SCENARIO_REGISTRY: dict[str, callable] = {
    "healthy_campaign": healthy_campaign,
    "good_ad_low_reachability": good_ad_low_reachability,
    "bad_ad_high_engagement": bad_ad_high_engagement,
    "small_sample_trap": small_sample_trap,
    "delayed_conversion_trap": delayed_conversion_trap,
    "creative_fatigue": creative_fatigue,
    "mixed_portfolio": mixed_portfolio,
    "high_cpql": high_cpql,
    "sudden_deterioration": sudden_deterioration,
}


def get_scenario(name: str, seed: int) -> ScenarioConfig:
    if name not in SCENARIO_REGISTRY:
        raise ValueError(
            f"Unknown scenario '{name}'. Available: {list(SCENARIO_REGISTRY.keys())}"
        )
    return SCENARIO_REGISTRY[name](seed)
