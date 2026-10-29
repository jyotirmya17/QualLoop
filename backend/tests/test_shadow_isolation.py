"""
Step 4D.10: Automated Isolation and Regression Tests for Shadow-Mode Foundation.

Validates:
1. Shadow evaluation cannot invoke ad-mutation functions or external platform clients.
2. Production decision remains 100% unaltered when shadow evaluation is invoked.
3. Language guardrails forbid misleading confidence claims (e.g. 95.8% confidence from p=0.042).
4. Idempotency prevents duplicate events when reprocessing identical snapshots.
5. Explicit abstention on missing or invalid business assumptions.
6. Explicit error recording on evaluator failure (no silent defaults).
7. Production audit trail is completely isolated from shadow events.
"""

from datetime import datetime, timezone
import inspect
from pathlib import Path
import sys
import uuid
import pytest

repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.audit.trail import query_decisions, query_audit_events
from backend.shadow.contracts import (
    BusinessAssumptionStatus,
    DecisionTimeSnapshot,
    ShadowAction,
    ShadowBusinessAssumptions,
    ShadowEconomicDecision,
    ShadowEconomicDecisionLoggedEvent,
)
from backend.shadow.runner import execute_shadow_evaluation
from backend.shadow.sink import InMemoryShadowEventSink
from backend.domain.models import EstimateSnapshot


class MockSnapshot:
    """Mock telemetry snapshot for offline shadow testing."""
    def __init__(
        self,
        advertisement_id: str = "ad-test-123",
        n_leads: int = 50,
        n_contacts: int = 30,
        n_mature_contacts: int = 25,
        k_qualified: int = 2,
        maturity_fraction: float = 0.85,
        reachability_mean: float = 0.60,
        qualification_mean: float = 0.08,
    ):
        self.id = f"snap-{advertisement_id}"
        self.advertisement_id = advertisement_id
        self.computed_at = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
        self.n_leads = n_leads
        self.n_contacts = n_contacts
        self.n_mature_contacts = n_mature_contacts
        self.n_mature_leads = n_leads
        self.k_qualified = k_qualified
        self.maturity_fraction_contact = maturity_fraction
        self.reachability_mean = reachability_mean
        self.qualification_mean = qualification_mean


def test_shadow_cannot_invoke_ad_mutation_or_external_clients():
    """Verify shadow package has zero references or imports of external mutation clients."""
    import backend.shadow.runner as runner
    import backend.shadow.contracts as contracts
    import backend.shadow.sink as sink

    modules = [runner, contracts, sink]
    forbidden_terms = [
        "requests.post",
        "requests.put",
        "requests.delete",
        "httpx.post",
        "httpx.put",
        "facebook_business",
        "googleads",
        "pause_campaign",
        "mutate",
        "update_status",
    ]

    for mod in modules:
        source = inspect.getsource(mod)
        for term in forbidden_terms:
            assert term not in source, f"Forbidden mutation pattern '{term}' found in {mod.__name__}"


def test_production_decision_unaltered():
    """Verify production decision is returned strictly unaltered by shadow runner."""
    sink = InMemoryShadowEventSink()
    snap = MockSnapshot()
    assumptions = ShadowBusinessAssumptions(
        lead_value=600.0,
        provenance="CLIENT_FINANCE_UPLOAD",
        config_version="v1.0",
    )

    prod_action = "CONTINUE"
    prod_reason = "Production heuristic: mature contacts below threshold."

    returned_action, event = execute_shadow_evaluation(
        snapshot=snap,
        cumulative_spend=2500.0,
        current_day=14.0,
        business_assumptions=assumptions,
        production_action=prod_action,
        production_reason=prod_reason,
        sink=sink,
    )

    assert returned_action == prod_action
    assert event.production_action_taken == prod_action
    assert event.production_reason == prod_reason
    assert event.is_shadow_only is True
    assert event.external_action_taken is False


def test_misleading_confidence_language_rejected():
    """
    Regression Test for Task 2:
    When probability_profitable = 0.042, it must not produce '95.8% confidence' or equivalent.
    Pydantic contract must reject events attempting to claim uncalibrated confidence.
    """
    snap_time = DecisionTimeSnapshot(
        snapshot_id="snap-1",
        advertisement_id="ad-1",
        computed_at=datetime.now(timezone.utc),
        cumulative_spend=1000.0,
        current_day=14.0,
        n_leads=30,
        n_contacts=20,
        n_mature_contacts=20,
        k_qualified=1,
        maturity_fraction_contact=0.8,
        reachability_mean=0.6,
        qualification_mean=0.05,
    )

    # 1. Verify that invalid reason claiming "95.8% confidence" is rejected by validator
    with pytest.raises(ValueError, match="(Misleading uncertainty language detected|Forbidden confidence claim detected)"):
        ShadowEconomicDecisionLoggedEvent(
            evaluator_version="v1",
            policy_version="v1",
            campaign_id="c-1",
            advertisement_id="ad-1",
            decision_time_snapshot=snap_time,
            shadow_decision=ShadowEconomicDecision(
                action=ShadowAction.PAUSE,
                reason="Expected CPQL (Rs 980.00) exceeds breakeven with 95.8% confidence.",
                exploratory_probability_profitable=0.042,
                calibration_status="EXPLORATORY_NOT_CALIBRATED",
            ),
            production_action_taken="CONTINUE",
            production_reason="Heuristic continue",
        )

    # 2. Verify that neutral exploratory language is accepted
    valid_event = ShadowEconomicDecisionLoggedEvent(
        evaluator_version="v1",
        policy_version="v1",
        campaign_id="c-1",
        advertisement_id="ad-1",
        decision_time_snapshot=snap_time,
        shadow_decision=ShadowEconomicDecision(
            action=ShadowAction.PAUSE,
            reason="Exploratory model projection indicates projected CPQL (Rs 980.00) exceeds breakeven. Exploratory model probability of profitability: 4.2% (uncalibrated estimate).",
            exploratory_probability_profitable=0.042,
            calibration_status="EXPLORATORY_NOT_CALIBRATED",
        ),
        production_action_taken="CONTINUE",
        production_reason="Heuristic continue",
    )
    assert valid_event.shadow_decision.exploratory_probability_profitable == 0.042
    assert "95.8% confidence" not in valid_event.shadow_decision.reason


def test_idempotent_event_sink():
    """Verify repeated processing of identical snapshot does not duplicate events."""
    sink = InMemoryShadowEventSink()
    snap = MockSnapshot()
    assumptions = ShadowBusinessAssumptions(
        lead_value=600.0,
        provenance="CLIENT_FINANCE_UPLOAD",
        config_version="v1.0",
    )

    # First run
    _, event1 = execute_shadow_evaluation(
        snapshot=snap, cumulative_spend=2500.0, current_day=14.0,
        business_assumptions=assumptions, production_action="CONTINUE",
        production_reason="Heuristic", sink=sink,
    )
    assert len(sink.query_events(advertisement_id=snap.advertisement_id)) == 1

    # Second run (identical snapshot and evaluator version)
    _, event2 = execute_shadow_evaluation(
        snapshot=snap, cumulative_spend=2500.0, current_day=14.0,
        business_assumptions=assumptions, production_action="CONTINUE",
        production_reason="Heuristic", sink=sink,
    )

    # Sink must remain at 1 event
    events = sink.query_events(advertisement_id=snap.advertisement_id)
    assert len(events) == 1
    assert events[0].event_id == event1.event_id


def test_missing_business_assumptions_abstains():
    """Verify missing lead_value results in explicit abstention without guessing universal constants."""
    sink = InMemoryShadowEventSink()
    snap = MockSnapshot()

    # Case A: assumptions is None
    _, event_none = execute_shadow_evaluation(
        snapshot=snap, cumulative_spend=2500.0, current_day=14.0,
        business_assumptions=None, production_action="CONTINUE",
        production_reason="Heuristic", sink=sink,
    )
    assert event_none.shadow_decision.action == ShadowAction.ABSTAIN_MISSING_ASSUMPTIONS
    assert "missing or unconfigured" in event_none.shadow_decision.reason

    # Case B: assumptions has lead_value = None
    assumptions_no_val = ShadowBusinessAssumptions(
        lead_value=None,
        provenance="PARTIAL_CONFIG",
        config_version="v0.1",
    )
    _, event_no_val = execute_shadow_evaluation(
        snapshot=snap, cumulative_spend=2500.0, current_day=14.0,
        business_assumptions=assumptions_no_val, production_action="CONTINUE",
        production_reason="Heuristic", sink=sink,
    )
    assert event_no_val.shadow_decision.action == ShadowAction.ABSTAIN_MISSING_ASSUMPTIONS


def test_evaluator_error_records_explicit_error():
    """Verify evaluator runtime errors are captured as ERROR, never defaulted to CONTINUE or PAUSE."""
    sink = InMemoryShadowEventSink()

    class BrokenSnapshot:
        advertisement_id = "ad-broken"
        id = "snap-broken"
        computed_at = datetime.now(timezone.utc)
        n_leads = 10
        n_contacts = "INVALID_TYPE_STRING"  # triggers TypeError inside math
        n_mature_contacts = 10
        n_mature_leads = 10
        k_qualified = 1
        maturity_fraction_contact = 0.8
        reachability_mean = 0.5
        qualification_mean = 0.1

    assumptions = ShadowBusinessAssumptions(
        lead_value=600.0,
        provenance="CLIENT_FINANCE_UPLOAD",
        config_version="v1.0",
    )

    _, event_err = execute_shadow_evaluation(
        snapshot=BrokenSnapshot(), cumulative_spend=1000.0, current_day=14.0,
        business_assumptions=assumptions, production_action="CONTINUE",
        production_reason="Heuristic", sink=sink,
    )

    assert event_err.shadow_decision.action == ShadowAction.ERROR
    assert "failure" in event_err.shadow_decision.reason.lower()


def test_production_audit_trail_completely_isolated():
    """Verify that shadow events are NOT persisted into production audit tables."""
    sink = InMemoryShadowEventSink()
    snap = MockSnapshot(advertisement_id="ad-audit-isolation-test")
    assumptions = ShadowBusinessAssumptions(
        lead_value=600.0,
        provenance="CLIENT_FINANCE_UPLOAD",
        config_version="v1.0",
    )

    execute_shadow_evaluation(
        snapshot=snap, cumulative_spend=2500.0, current_day=14.0,
        business_assumptions=assumptions, production_action="CONTINUE",
        production_reason="Heuristic", sink=sink,
    )

    # Production audit store must NOT contain any decision or event for this ad
    prod_decisions = query_decisions(advertisement_id="ad-audit-isolation-test")
    assert len(prod_decisions) == 0

    prod_events = query_audit_events()
    assert not any(getattr(e, "advertisement_id", None) == "ad-audit-isolation-test" for e in prod_events)
