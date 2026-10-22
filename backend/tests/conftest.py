"""
pytest configuration and shared fixtures.
"""

import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from domain.enums import CallOutcome, LeadStatus, QualificationResult
from domain.models import (
    Advertisement, AdSet, Campaign, Lead, CallAttempt,
    QualificationOutcome, SimulationRun,
)
from simulator.scenarios import healthy_campaign
from simulator.engine import run_simulation


@pytest.fixture
def rng():
    """Fixed-seed numpy RNG for reproducible tests."""
    return np.random.default_rng(42)


@pytest.fixture
def now():
    return datetime(2025, 2, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def healthy_simulation():
    """A fully run healthy_campaign simulation result."""
    config = healthy_campaign(seed=42)
    return run_simulation(config)


@pytest.fixture
def simple_ad():
    return Advertisement(
        id="ad-test-001",
        ad_set_id="as-test-001",
        creative_id="creative-test-A",
        spend=5000.0,
        impressions=50000,
        clicks=2000,
    )


@pytest.fixture
def mature_leads_with_calls(now):
    """
    40 mature leads, 28 contacted (answered), 10 qualified, 18 disqualified.
    Contact made 9 days ago (past 7-day qual window).
    """
    leads = [
        Lead(
            id=f"lead-{i:03d}",
            advertisement_id="ad-test-001",
            created_at=now - timedelta(days=15),
            status=LeadStatus.SUBMITTED,
        )
        for i in range(40)
    ]

    calls = [
        CallAttempt(
            id=f"call-{i:03d}",
            lead_id=f"lead-{i:03d}",
            attempted_at=now - timedelta(days=9),
            outcome=CallOutcome.ANSWERED,
        )
        for i in range(28)
    ] + [
        CallAttempt(
            id=f"call-fail-{i:03d}",
            lead_id=f"lead-{i:03d}",
            attempted_at=now - timedelta(days=9),
            outcome=CallOutcome.NO_ANSWER,
        )
        for i in range(28, 40)
    ]

    quals = [
        QualificationOutcome(
            id=f"qual-{i:03d}",
            lead_id=f"lead-{i:03d}",
            resolved_at=now - timedelta(days=7, hours=1),
            result=QualificationResult.QUALIFIED,
        )
        for i in range(10)
    ] + [
        QualificationOutcome(
            id=f"qual-dis-{i:03d}",
            lead_id=f"lead-{i:03d}",
            resolved_at=now - timedelta(days=7, hours=1),
            result=QualificationResult.DISQUALIFIED,
        )
        for i in range(10, 28)
    ]

    return leads, calls, quals
