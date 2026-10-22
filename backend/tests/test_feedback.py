"""
Tests for the Meta CAPI feedback event builder.

Tests verify:
- Only QUALIFIED outcomes are accepted
- PII is SHA-256 hashed
- Event timestamps are validated (not future, not older than 7 days)
- Idempotency key is deterministic (same inputs → same key)
- Different inputs → different idempotency keys
- payload structure matches Meta CAPI v21.0 requirements
- validate_payload catches missing required fields
"""

import hashlib
import pytest
from datetime import datetime, timedelta, timezone

from domain.enums import QualificationResult, LeadStatus
from domain.models import Lead, QualificationOutcome
from feedback.builder import build_event, validate_payload, ValidationError


def _make_lead(lead_id: str = "lead-001") -> Lead:
    return Lead(
        id=lead_id,
        advertisement_id="ad-001",
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        status=LeadStatus.QUALIFIED,
    )


def _make_qualified_outcome(lead_id: str = "lead-001", days_ago: float = 1.0) -> QualificationOutcome:
    return QualificationOutcome(
        id=f"outcome-{lead_id}",
        lead_id=lead_id,
        resolved_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        result=QualificationResult.QUALIFIED,
    )


def _make_disqualified_outcome(lead_id: str = "lead-001") -> QualificationOutcome:
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
            lead_id="lead-001",
            resolved_at=datetime.now(timezone.utc) + timedelta(days=1),  # future!
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("future" in e.message.lower() for e in result.validation_errors)

    def test_old_event_is_rejected(self):
        lead = _make_lead()
        outcome = QualificationOutcome(
            id="outcome-old",
            lead_id="lead-001",
            resolved_at=datetime.now(timezone.utc) - timedelta(days=8),  # too old
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("7 days" in e.message for e in result.validation_errors)

    def test_event_name_is_correct(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.event.event_name == "Lead"

    def test_action_source_is_crm(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.event.action_source == "crm"

    def test_user_data_contains_hashed_fields(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")
        user_data = result.event.user_data
        assert "em" in user_data
        assert "ph" in user_data
        # Values should be 64-character hex strings (SHA-256)
        assert len(user_data["em"]) == 64
        assert len(user_data["ph"]) == 64

    def test_custom_data_contains_lead_and_ad_ids(self):
        lead = _make_lead("lead-007")
        outcome = _make_qualified_outcome("lead-007")
        result = build_event(outcome, lead, ad_id="ad-777")
        custom = result.event.custom_data
        assert custom["lead_id"] == "lead-007"
        assert custom["ad_id"] == "ad-777"

    def test_dry_run_mode_sets_processing_status(self):
        from domain.enums import FeedbackProcessingStatus
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001", dry_run=True)
        assert result.event.processing_status == FeedbackProcessingStatus.DRY_RUN


class TestIdempotencyKey:
    def test_same_inputs_produce_same_key(self):
        lead = _make_lead("lead-A")
        outcome = _make_qualified_outcome("lead-A")
        result1 = build_event(outcome, lead, ad_id="ad-001")
        result2 = build_event(outcome, lead, ad_id="ad-001")
        assert result1.idempotency_key == result2.idempotency_key

    def test_different_lead_ids_produce_different_keys(self):
        lead_a = _make_lead("lead-A")
        lead_b = _make_lead("lead-B")
        outcome_a = _make_qualified_outcome("lead-A")
        outcome_b = _make_qualified_outcome("lead-B")
        result_a = build_event(outcome_a, lead_a, ad_id="ad-001")
        result_b = build_event(outcome_b, lead_b, ad_id="ad-001")
        assert result_a.idempotency_key != result_b.idempotency_key

    def test_idempotency_key_is_32_chars(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        result = build_event(outcome, lead, ad_id="ad-001")
        assert len(result.idempotency_key) == 32


class TestValidatePayload:
    def test_valid_event_passes_validation(self):
        lead = _make_lead()
        outcome = _make_qualified_outcome()
        build_result = build_event(outcome, lead, ad_id="ad-001")
        errors = validate_payload(build_result.event)
        assert errors == []

    def test_missing_event_name_fails(self):
        from domain.models import FeedbackEvent
        from domain.enums import FeedbackValidationStatus, FeedbackProcessingStatus
        event = FeedbackEvent(
            qualification_outcome_id="o1",
            idempotency_key="abc123",
            event_name="",  # missing!
            event_time=1000000,
            action_source="crm",
            user_data={"em": "abc"},
            custom_data={},
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        )
        errors = validate_payload(event)
        assert any(e.field == "event_name" for e in errors)

    def test_zero_event_time_fails(self):
        from domain.models import FeedbackEvent
        from domain.enums import FeedbackValidationStatus, FeedbackProcessingStatus
        event = FeedbackEvent(
            qualification_outcome_id="o1",
            idempotency_key="abc123",
            event_name="Lead",
            event_time=0,  # invalid!
            action_source="crm",
            user_data={"em": "abc"},
            custom_data={},
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        )
        errors = validate_payload(event)
        assert any(e.field == "event_time" for e in errors)

    def test_empty_user_data_fails(self):
        from domain.models import FeedbackEvent
        from domain.enums import FeedbackValidationStatus, FeedbackProcessingStatus
        event = FeedbackEvent(
            qualification_outcome_id="o1",
            idempotency_key="abc123",
            event_name="Lead",
            event_time=1000000,
            action_source="crm",
            user_data={},  # empty!
            custom_data={},
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN,
            created_at=datetime.now(timezone.utc),
        )
        errors = validate_payload(event)
        assert any(e.field == "user_data" for e in errors)

    def test_user_data_contains_unhashed_lead_id(self):
        """Verified CAPI requirement: lead_id must be in user_data as an unhashed string."""
        lead = _make_lead("meta-lead-123456789")
        outcome = _make_qualified_outcome("meta-lead-123456789")
        result = build_event(outcome, lead, ad_id="ad-001")

        assert result.is_valid is True
        user_data = result.event.user_data
        assert "lead_id" in user_data
        assert user_data["lead_id"] == "meta-lead-123456789"
        # lead_id must NOT be hashed
        assert len(user_data["lead_id"]) != 64

    def test_conversion_exceeding_28_day_window_is_rejected(self):
        """Verified Conversion Leads requirement: qualification must occur within 28 days of lead creation."""
        now = datetime.now(timezone.utc)
        lead = Lead(
            id="lead-old-funnel",
            advertisement_id="ad-001",
            created_at=now - timedelta(days=35),  # 35 days ago
            status=LeadStatus.QUALIFIED,
        )
        outcome = QualificationOutcome(
            id="outcome-late",
            lead_id="lead-old-funnel",
            resolved_at=now - timedelta(days=2),  # resolved 2 days ago (33 days after creation)
            result=QualificationResult.QUALIFIED,
        )
        result = build_event(outcome, lead, ad_id="ad-001")
        assert result.is_valid is False
        assert any("28" in e.message for e in result.validation_errors)

