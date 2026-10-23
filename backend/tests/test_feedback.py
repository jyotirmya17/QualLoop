"""
Tests for the Meta CAPI feedback event builder.

Tests verify official Meta Conversion Leads specifications:
- action_source must be "system_generated"
- custom_data must include lead_event_source and event_source="crm"
- lead_id goes in user_data, unhashed; emails/phones hashed
- emit a raw-lead event for every lead, plus one event per status change (full history, not a snapshot), each with a distinct stage name
- validate event_time is after lead creation and within 7 days of upload
- enforce a 1,000-event batch limit with per-batch validation
- warning-level fit checks: at least 200 leads per month, target stage rate between 1% and 40%
"""

import hashlib
from datetime import datetime, timedelta, timezone
import pytest

from domain.enums import CallOutcome, FeedbackProcessingStatus, FeedbackValidationStatus, LeadStatus, QualificationResult
from domain.models import CallAttempt, FeedbackEvent, Lead, QualificationOutcome
from feedback.builder import (
    CAPI_ACTION_SOURCE,
    CAPI_MAX_BATCH_SIZE,
    DEFAULT_CRM_NAME,
    DEFAULT_EVENT_SOURCE,
    BuildResult,
    ValidationError,
    build_event,
    build_lead_history_events,
    check_business_fit,
    chunk_into_batches,
    validate_batch,
    validate_payload,
)


def _make_lead(lead_id: str = "1000000000000001", days_ago: float = 5.0) -> Lead:
    return Lead(
        id=lead_id,
        advertisement_id="ad-001",
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        status=LeadStatus.QUALIFIED,
    )


def _make_qualified_outcome(lead_id: str = "1000000000000001", days_ago: float = 1.0) -> QualificationOutcome:
    return QualificationOutcome(
        id=f"outcome-{lead_id}",
        lead_id=lead_id,
        resolved_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        result=QualificationResult.QUALIFIED,
    )


def _make_disqualified_outcome(lead_id: str = "1000000000000001") -> QualificationOutcome:
    return QualificationOutcome(
        id=f"outcome-dis-{lead_id}",
        lead_id=lead_id,
        resolved_at=datetime.now(timezone.utc) - timedelta(days=1),
        result=QualificationResult.DISQUALIFIED,
    )


class TestBuildEvent:
    def test_qualified_lead_produces_valid_event(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")

        assert result.is_valid is True
        assert result.event is not None
        assert len(result.validation_errors) == 0

    def test_disqualified_outcome_is_rejected(self):
        lead = _make_lead()
        outcome = _make_disqualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")

        assert result.is_valid is False
        assert result.event is None
        assert any("QUALIFIED" in e.message for e in result.validation_errors)

    def test_future_timestamp_is_rejected(self):
        lead = _make_lead()
        outcome = QualificationOutcome(
            id="outcome-future",
            lead_id="1000000000000001",
            resolved_at=datetime.now(timezone.utc) + timedelta(days=1),
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("future" in e.message.lower() for e in result.validation_errors)

    def test_old_event_is_rejected(self):
        lead = _make_lead(days_ago=10.0)
        outcome = QualificationOutcome(
            id="outcome-old",
            lead_id="1000000000000001",
            resolved_at=datetime.now(timezone.utc) - timedelta(days=8),
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("7 days" in e.message for e in result.validation_errors)

    def test_event_before_lead_creation_is_rejected(self):
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="1000000000000002",
            advertisement_id="ad-001",
            created_at=now - timedelta(days=2),
            status=LeadStatus.QUALIFIED,
        )
        outcome = QualificationOutcome(
            id="outcome-inverted",
            lead_id="1000000000000002",
            resolved_at=now - timedelta(days=3),  # Before lead was created!
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("before lead creation" in e.message for e in result.validation_errors)

    def test_action_source_is_system_generated(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.event.action_source == "system_generated"

    def test_custom_data_contains_lead_event_source_and_event_source(self):
        lead = _make_lead("1000000000000007")
        outcome = _make_qualified_outcome("1000000000000007")
        result = build_event(outcome, lead, ad_id="ad-777", crm_name="Salesforce")
        custom = result.event.custom_data
        assert custom["lead_event_source"] == "Salesforce"
        assert custom["event_source"] == "crm"
        assert custom["lead_id"] == "1000000000000007"
        assert custom["ad_id"] == "ad-777"

    def test_user_data_unhashed_lead_id_and_hashed_pii(self):
        lead = _make_lead("9876543210987654")
        outcome = _make_qualified_outcome("9876543210987654")
        result = build_event(outcome, lead, ad_id="ad-001")
        user_data = result.event.user_data
        assert user_data["lead_id"] == "9876543210987654"
        assert len(user_data["lead_id"]) != 64  # not hashed
        assert len(user_data["em"]) == 64  # hashed SHA-256
        assert len(user_data["ph"]) == 64  # hashed SHA-256

    def test_conversion_exceeding_28_day_window_is_rejected(self):
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="1000000000000003",
            advertisement_id="ad-001",
            created_at=now - timedelta(days=35),
            status=LeadStatus.QUALIFIED,
        )
        outcome = QualificationOutcome(
            id="outcome-late",
            lead_id="1000000000000003",
            resolved_at=now - timedelta(days=2),
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("28" in e.message for e in result.validation_errors)


class TestFullLifecycleHistoryEvents:
    def test_emits_raw_lead_event_and_status_changes_with_distinct_stage_names(self):
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="1000000000000004",
            advertisement_id="ad-001",
            created_at=now - timedelta(days=4),
            status=LeadStatus.QUALIFIED,
        )
        calls = [
            CallAttempt(
                id="call-1",
                lead_id=lead.id,
                attempted_at=now - timedelta(days=3),
                outcome=CallOutcome.NO_ANSWER,
            ),
            CallAttempt(
                id="call-2",
                lead_id=lead.id,
                attempted_at=now - timedelta(days=2),
                outcome=CallOutcome.ANSWERED,
            ),
        ]
        outcome = QualificationOutcome(
            id="outcome-qual-1",
            lead_id=lead.id,
            resolved_at=now - timedelta(days=1),
            result=QualificationResult.QUALIFIED,
        )

        history_results = build_lead_history_events(
            lead=lead,
            ad_id="ad-001",
            call_attempts=calls,
            qualification_outcome=outcome,
            crm_name="Salesforce",
        )

        assert len(history_results) == 4
        assert all(r.is_valid for r in history_results)

        stage_names = [r.event.event_name for r in history_results]
        # Must emit raw lead event, distinct call attempt stages, and qualification stage
        assert stage_names == ["initial_lead", "call_attempted", "contacted", "qualified"]

        # Check action_source and custom_data on all events
        for r in history_results:
            assert r.event.action_source == "system_generated"
            assert r.event.custom_data["lead_event_source"] == "Salesforce"
            assert r.event.custom_data["event_source"] == "crm"
            assert r.event.user_data["lead_id"] == lead.id

    def test_rejects_status_change_before_lead_creation(self):
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="1000000000000005",
            advertisement_id="ad-001",
            created_at=now - timedelta(days=2),
            status=LeadStatus.SUBMITTED,
        )
        bad_calls = [
            CallAttempt(
                id="call-before",
                lead_id=lead.id,
                attempted_at=now - timedelta(days=3),  # Before lead creation!
                outcome=CallOutcome.ANSWERED,
            )
        ]
        history = build_lead_history_events(lead, "ad-001", call_attempts=bad_calls)
        call_res = next(r for r in history if "call" in r.idempotency_key or r.event is None)
        assert call_res.is_valid is False
        assert any("before lead creation" in e.message for e in call_res.validation_errors)


class TestBatchValidationAndLimits:
    def test_batch_within_limit_passes(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        event = build_event(outcome, lead, "ad-001").event

        batch = [event] * 50
        errors = validate_batch(batch)
        assert errors == []

    def test_batch_exceeding_1000_events_fails(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        event = build_event(outcome, lead, "ad-001").event

        batch = [event] * 1001
        errors = validate_batch(batch)
        assert any(e.field == "batch_size" for e in errors)
        assert any("1,000" in e.message or "1000" in e.message for e in errors)

    def test_chunk_into_batches(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        event = build_event(outcome, lead, "ad-001").event

        events = [event] * 2500
        batches = chunk_into_batches(events, batch_size=1000)
        assert len(batches) == 3
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 1000
        assert len(batches[2]) == 500


class TestBusinessFitChecks:
    def test_acceptable_business_fit(self):
        # 300 leads/month, 15% conversion rate
        result = check_business_fit(monthly_leads=300, target_stage_conversion_rate=0.15)
        assert result.is_fit is True
        assert len(result.warnings) == 0

    def test_low_monthly_lead_volume_warning(self):
        # 120 leads/month (< 200)
        result = check_business_fit(monthly_leads=120, target_stage_conversion_rate=0.15)
        assert result.is_fit is False
        assert any("200 leads/month" in w for w in result.warnings)

    def test_conversion_rate_outside_recommended_range(self):
        # 0.5% (< 1%)
        result_low = check_business_fit(monthly_leads=500, target_stage_conversion_rate=0.005)
        assert result_low.is_fit is False
        assert any("1%-40%" in w for w in result_low.warnings)

        # 55% (> 40%)
        result_high = check_business_fit(monthly_leads=500, target_stage_conversion_rate=0.55)
        assert result_high.is_fit is False
        assert any("1%-40%" in w for w in result_high.warnings)


class TestValidatePayload:
    def test_valid_event_passes_validation(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        build_result = build_event(outcome, lead, ad_id="ad-001")
        errors = validate_payload(build_result.event)
        assert errors == []

    def test_missing_event_name_fails(self):
        event = FeedbackEvent(
            qualification_outcome_id="o1",
            idempotency_key="abc123",
            event_name="",
            event_time=int(datetime.now(timezone.utc).timestamp()) - 100,
            action_source="system_generated",
            user_data={"lead_id": "1000000000000001"},
            custom_data={"lead_event_source": "Salesforce", "event_source": "crm"},
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        )
        errors = validate_payload(event)
        assert any(e.field == "event_name" for e in errors)

    def test_invalid_action_source_fails(self):
        event = FeedbackEvent(
            qualification_outcome_id="o1",
            idempotency_key="abc123",
            event_name="qualified",
            event_time=int(datetime.now(timezone.utc).timestamp()) - 100,
            action_source="website",  # Must be system_generated
            user_data={"lead_id": "1000000000000001"},
            custom_data={"lead_event_source": "Salesforce", "event_source": "crm"},
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        )
        errors = validate_payload(event)
        assert any(e.field == "action_source" for e in errors)

    def test_missing_lead_event_source_fails(self):
        event = FeedbackEvent(
            qualification_outcome_id="o1",
            idempotency_key="abc123",
            event_name="qualified",
            event_time=int(datetime.now(timezone.utc).timestamp()) - 100,
            action_source="system_generated",
            user_data={"lead_id": "1000000000000001"},
            custom_data={"event_source": "crm"},  # missing lead_event_source!
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        )
        errors = validate_payload(event)
        assert any("lead_event_source" in e.field for e in errors)

    def test_reject_invalid_lead_id_format(self):
        """Reject lead_ids that are not 15-17 digit strings."""
        invalid_ids = [
            "lead-001",
            "12345",
            "12345678901234",  # 14 digits (too short)
            "123456789012345678",  # 18 digits (too long)
            "meta_lead_123456",
            "123456789012345a",  # contains non-digit
            "",
        ]
        for bad_id in invalid_ids:
            # Rejection in build_event
            lead = Lead(
                id=bad_id,
                advertisement_id="ad-001",
                created_at=datetime.now(timezone.utc) - timedelta(days=2),
                status=LeadStatus.QUALIFIED,
            )
            outcome = QualificationOutcome(
                id="out-bad",
                lead_id=bad_id,
                resolved_at=datetime.now(timezone.utc) - timedelta(days=1),
                result=QualificationResult.QUALIFIED,
            )
            res = build_event(outcome, lead, ad_id="ad-001")
            assert res.is_valid is False
            assert any("15-17 digit" in e.message for e in res.validation_errors)

            # Rejection in validate_payload
            event = FeedbackEvent(
                qualification_outcome_id="o1",
                idempotency_key="idemp_bad",
                event_name="qualified",
                event_time=int(datetime.now(timezone.utc).timestamp()) - 100,
                action_source="system_generated",
                user_data={"lead_id": bad_id},
                custom_data={"lead_event_source": "Salesforce", "event_source": "crm"},
                validation_status=FeedbackValidationStatus.VALID,
                processing_status=FeedbackProcessingStatus.DRY_RUN,
                created_at=datetime.now(timezone.utc),
            )
            errors = validate_payload(event)
            assert any("15-17 digit" in e.message or "identifier" in e.message for e in errors)

    def test_qualified_stage_event_name_is_qualified(self):
        lead = _make_lead("1000000000000009")
        outcome = _make_qualified_outcome("1000000000000009")
        res = build_event(outcome, lead, ad_id="ad-001")
        assert res.is_valid is True
        assert res.event is not None
        assert res.event.event_name == "qualified"
        assert res.event.event_name != "Lead"

