"""
Meta Conversions API feedback event builder for Conversion Leads.

Builds and validates event payloads for Meta's Conversions API for CRM integration.
Runs in dry-run mode by default — no HTTP calls are made.

ARCHITECTURE BOUNDARY:
- This module builds and validates payloads. It does not send them.
- A future transmitter module handles live HTTP transmission if credentials exist.
- Official reference:
  - https://developers.facebook.com/documentation/ads-commerce/conversions-api/conversion-leads-integration
  - https://developers.facebook.com/documentation/ads-commerce/conversions-api/conversion-leads-integration/crm-integration/3-implementing-the-crm-integration
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

LEAD_ID_REGEX = re.compile(r"^\d{15,17}$")


def is_valid_lead_id(lead_id: Any) -> bool:
    """Validate whether lead_id is a 15-17 digit numeric string as assigned by Meta."""
    if not lead_id:
        return False
    return bool(LEAD_ID_REGEX.match(str(lead_id).strip()))

from domain.enums import (
    CallOutcome,
    FeedbackProcessingStatus,
    FeedbackValidationStatus,
    LeadStatus,
    QualificationResult,
)
from domain.models import CallAttempt, FeedbackEvent, Lead, QualificationOutcome

logger = structlog.get_logger(__name__)

# Meta CAPI specification constants (Verified against official Meta documentation)
CAPI_ACTION_SOURCE = "system_generated"
DEFAULT_CRM_NAME = "QualLoopCRM"
DEFAULT_EVENT_SOURCE = "crm"
CAPI_EVENT_NAME_QUALIFIED = "qualified"
CAPI_EVENT_NAME_INITIAL_LEAD = "initial_lead"

# Event timing and batch constraints
CAPI_MAX_UPLOAD_AGE_DAYS = 7.0  # Meta CAPI hard rejection limit (upload_time - event_time <= 7 days)
CAPI_MAX_CONVERSION_WINDOW_DAYS = 28.0  # Conversion Leads attribution window
CAPI_MAX_BATCH_SIZE = 1000  # Meta maximum events per batch request


@dataclass
class ValidationError:
    field: str
    message: str


@dataclass
class BuildResult:
    """Result of attempting to build a feedback event."""

    event: Optional[FeedbackEvent]
    validation_errors: list[ValidationError]
    is_valid: bool
    idempotency_key: str


@dataclass
class FitCheckResult:
    """Warning-level fit check for Meta Conversion Leads optimization."""

    is_fit: bool
    warnings: list[str]


def check_business_fit(
    monthly_leads: int,
    target_stage_conversion_rate: float,
) -> FitCheckResult:
    """
    Check if account volume and stage conversion rate meet Meta's recommended guidelines.

    Guidelines from official Meta Conversion Leads documentation:
    - At least 200 leads per month
    - Target stage conversion rate between 1% and 40% (0.01 to 0.40)
    """
    warnings: list[str] = []

    if monthly_leads < 200:
        warnings.append(
            f"Monthly lead volume ({monthly_leads}) is below Meta's recommended minimum of 200 leads/month for Conversion Leads optimization."
        )

    if target_stage_conversion_rate < 0.01 or target_stage_conversion_rate > 0.40:
        warnings.append(
            f"Target stage conversion rate ({target_stage_conversion_rate:.1%}) is outside Meta's recommended 1%-40% range for model optimization."
        )

    return FitCheckResult(is_fit=len(warnings) == 0, warnings=warnings)


def build_event(
    qualification_outcome: QualificationOutcome,
    lead: Lead,
    ad_id: str,
    campaign_name: str = "",
    crm_name: str = DEFAULT_CRM_NAME,
    upload_time: Optional[datetime] = None,
    dry_run: bool = True,
) -> BuildResult:
    """
    Build a validated Meta CAPI event payload for a qualified lead.

    Args:
        qualification_outcome: The resolved qualification outcome (must be QUALIFIED)
        lead: The lead record
        ad_id: The advertisement ID for custom_data
        campaign_name: Optional campaign name for custom_data
        crm_name: Name of advertiser CRM for custom_data.lead_event_source
        upload_time: Timestamp of upload batch (defaults to current UTC time)
        dry_run: If True, event will be logged but not transmitted (default: True)
    """
    idempotency_key = _make_idempotency_key(qualification_outcome.id, lead.id)
    errors: list[ValidationError] = []

    # Validate lead_id format (must be 15-17 digit string from Meta Instant Forms)
    if not is_valid_lead_id(lead.id):
        errors.append(
            ValidationError(
                field="lead.id",
                message=(
                    f"lead_id must be a 15-17 digit numeric string as assigned by Meta. "
                    f"Got: '{lead.id}'"
                ),
            )
        )

    # Validate qualification status
    if qualification_outcome.result != QualificationResult.QUALIFIED:
        errors.append(
            ValidationError(
                field="qualification_outcome.result",
                message=(
                    f"Only QUALIFIED outcomes should be sent to Meta CAPI. "
                    f"Got: {qualification_outcome.result.value}"
                ),
            )
        )

    # Validate resolved_at timestamp
    now = upload_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_ts = now.timestamp()

    resolved_ts = qualification_outcome.resolved_at
    if resolved_ts.tzinfo is None:
        resolved_ts = resolved_ts.replace(tzinfo=timezone.utc)
    event_time_unix = int(resolved_ts.timestamp())

    # Timestamp cannot be in future
    if event_time_unix > int(now_ts):
        errors.append(
            ValidationError(
                field="qualification_outcome.resolved_at",
                message="Event time is in the future — timestamps must not be future-dated",
            )
        )

    # Timestamp must be after lead creation
    lead_created_ts = lead.created_at
    if lead_created_ts.tzinfo is None:
        lead_created_ts = lead_created_ts.replace(tzinfo=timezone.utc)
    if resolved_ts < lead_created_ts:
        errors.append(
            ValidationError(
                field="event_time",
                message=(
                    f"Event time ({resolved_ts.isoformat()}) is before lead creation time "
                    f"({lead_created_ts.isoformat()}) — events must occur after lead creation."
                ),
            )
        )

    # Validate event_time upload age (Meta CAPI hard limit: event_time within 7 days of upload)
    age_days = (now_ts - event_time_unix) / 86400.0
    if age_days > CAPI_MAX_UPLOAD_AGE_DAYS:
        errors.append(
            ValidationError(
                field="qualification_outcome.resolved_at",
                message=(
                    f"Event upload age is {age_days:.1f} days. "
                    f"Meta CAPI rejects events with event_time older than {CAPI_MAX_UPLOAD_AGE_DAYS:.0f} days."
                ),
            )
        )

    # Validate conversion attribution window (Meta Conversion Leads limit: resolved within 28 days of lead creation)
    conversion_days = (resolved_ts.timestamp() - lead_created_ts.timestamp()) / 86400.0
    if conversion_days > CAPI_MAX_CONVERSION_WINDOW_DAYS:
        errors.append(
            ValidationError(
                field="lead.created_at",
                message=(
                    f"Qualification occurred {conversion_days:.1f} days after lead creation, "
                    f"exceeding Meta's {CAPI_MAX_CONVERSION_WINDOW_DAYS:.0f}-day conversion optimization window."
                ),
            )
        )

    # Build user_data with unhashed lead_id and synthetic hashed PII
    user_data = _build_user_data_synthetic(lead.id)

    # Build custom_data matching official Meta Conversion Leads specification
    custom_data: dict[str, Any] = {
        "lead_event_source": crm_name,
        "event_source": DEFAULT_EVENT_SOURCE,
        "lead_id": str(lead.id),
        "ad_id": ad_id,
        "qualification_outcome_id": qualification_outcome.id,
    }
    if campaign_name:
        custom_data["campaign_name"] = campaign_name

    if errors:
        logger.warning(
            "feedback_event_validation_failed",
            lead_id=lead.id,
            outcome_id=qualification_outcome.id,
            errors=[{"field": e.field, "message": e.message} for e in errors],
        )
        return BuildResult(
            event=None,
            validation_errors=errors,
            is_valid=False,
            idempotency_key=idempotency_key,
        )

    processing_status = (
        FeedbackProcessingStatus.DRY_RUN if dry_run else FeedbackProcessingStatus.SENT
    )

    event = FeedbackEvent(
        qualification_outcome_id=qualification_outcome.id,
        idempotency_key=idempotency_key,
        event_name=CAPI_EVENT_NAME_QUALIFIED,
        event_time=event_time_unix,
        action_source=CAPI_ACTION_SOURCE,
        user_data=user_data,
        custom_data=custom_data,
        validation_status=FeedbackValidationStatus.VALID,
        processing_status=processing_status,
        created_at=datetime.now(timezone.utc),
    )

    return BuildResult(
        event=event,
        validation_errors=[],
        is_valid=True,
        idempotency_key=idempotency_key,
    )


def build_lead_history_events(
    lead: Lead,
    ad_id: str,
    call_attempts: Optional[list[CallAttempt]] = None,
    qualification_outcome: Optional[QualificationOutcome] = None,
    crm_name: str = DEFAULT_CRM_NAME,
    campaign_name: str = "",
    upload_time: Optional[datetime] = None,
    dry_run: bool = True,
) -> list[BuildResult]:
    """
    Emit full lead status change history (not just a point-in-time snapshot).

    Official Meta Requirement:
    - Capture the lead status change history rather than a snapshot.
    - Emit a raw-lead event for every lead ("initial_lead"), plus one event per status change
      (e.g., "call_attempted", "contacted", "qualified"), each with a distinct stage name.
    - Validate event_time is after lead creation and within 7 days of upload.
    """
    results: list[BuildResult] = []
    now = upload_time or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_ts = now.timestamp()

    lead_created_ts = lead.created_at
    if lead_created_ts.tzinfo is None:
        lead_created_ts = lead_created_ts.replace(tzinfo=timezone.utc)

    # Validate lead_id format
    if not is_valid_lead_id(lead.id):
        return [
            BuildResult(
                event=None,
                validation_errors=[
                    ValidationError(
                        field="lead.id",
                        message=f"lead_id must be a 15-17 digit numeric string as assigned by Meta. Got: '{lead.id}'",
                    )
                ],
                is_valid=False,
                idempotency_key=_make_idempotency_key("invalid_lead", str(lead.id)),
            )
        ]

    # 1. Raw-lead event for initial lead creation
    lead_idemp = _make_idempotency_key("initial_lead", lead.id)
    raw_event_time = int(lead_created_ts.timestamp())
    raw_errors: list[ValidationError] = []

    if raw_event_time > int(now_ts):
        raw_errors.append(
            ValidationError("event_time", "Event time is in the future")
        )
    raw_age_days = (now_ts - raw_event_time) / 86400.0
    if raw_age_days > CAPI_MAX_UPLOAD_AGE_DAYS:
        raw_errors.append(
            ValidationError(
                "event_time",
                f"Initial lead event age ({raw_age_days:.1f} days) exceeds 7-day upload limit",
            )
        )

    if raw_errors:
        results.append(
            BuildResult(
                event=None,
                validation_errors=raw_errors,
                is_valid=False,
                idempotency_key=lead_idemp,
            )
        )
    else:
        custom_data_raw = {
            "lead_event_source": crm_name,
            "event_source": DEFAULT_EVENT_SOURCE,
            "lead_id": str(lead.id),
            "ad_id": ad_id,
            "stage": CAPI_EVENT_NAME_INITIAL_LEAD,
        }
        if campaign_name:
            custom_data_raw["campaign_name"] = campaign_name
        event_raw = FeedbackEvent(
            qualification_outcome_id=f"init_{lead.id}",
            idempotency_key=lead_idemp,
            event_name=CAPI_EVENT_NAME_INITIAL_LEAD,
            event_time=raw_event_time,
            action_source=CAPI_ACTION_SOURCE,
            user_data=_build_user_data_synthetic(lead.id),
            custom_data=custom_data_raw,
            validation_status=FeedbackValidationStatus.VALID,
            processing_status=FeedbackProcessingStatus.DRY_RUN if dry_run else FeedbackProcessingStatus.SENT,
            created_at=datetime.now(timezone.utc),
        )
        results.append(
            BuildResult(
                event=event_raw,
                validation_errors=[],
                is_valid=True,
                idempotency_key=lead_idemp,
            )
        )

    # 2. Subsequent status change events (call attempts / contacts)
    sorted_calls = sorted(call_attempts or [], key=lambda c: c.attempted_at)
    for call in sorted_calls:
        call_time = call.attempted_at
        if call_time.tzinfo is None:
            call_time = call_time.replace(tzinfo=timezone.utc)
        call_time_unix = int(call_time.timestamp())

        stage_name = "contacted" if call.outcome == CallOutcome.ANSWERED else "call_attempted"
        call_idemp = _make_idempotency_key(f"call_{call.id}_{stage_name}", lead.id)
        call_errors: list[ValidationError] = []

        if call_time_unix > int(now_ts):
            call_errors.append(ValidationError("event_time", "Event time is in the future"))
        if call_time < lead_created_ts:
            call_errors.append(
                ValidationError(
                    "event_time",
                    f"Call event time ({call_time.isoformat()}) is before lead creation ({lead_created_ts.isoformat()})",
                )
            )
        call_age_days = (now_ts - call_time_unix) / 86400.0
        if call_age_days > CAPI_MAX_UPLOAD_AGE_DAYS:
            call_errors.append(
                ValidationError(
                    "event_time",
                    f"Call event age ({call_age_days:.1f} days) exceeds 7-day upload limit",
                )
            )

        if call_errors:
            results.append(
                BuildResult(
                    event=None,
                    validation_errors=call_errors,
                    is_valid=False,
                    idempotency_key=call_idemp,
                )
            )
        else:
            custom_data_call = {
                "lead_event_source": crm_name,
                "event_source": DEFAULT_EVENT_SOURCE,
                "lead_id": str(lead.id),
                "ad_id": ad_id,
                "stage": stage_name,
                "call_outcome": call.outcome.value,
            }
            if campaign_name:
                custom_data_call["campaign_name"] = campaign_name
            event_call = FeedbackEvent(
                qualification_outcome_id=f"call_{call.id}",
                idempotency_key=call_idemp,
                event_name=stage_name,
                event_time=call_time_unix,
                action_source=CAPI_ACTION_SOURCE,
                user_data=_build_user_data_synthetic(lead.id),
                custom_data=custom_data_call,
                validation_status=FeedbackValidationStatus.VALID,
                processing_status=FeedbackProcessingStatus.DRY_RUN if dry_run else FeedbackProcessingStatus.SENT,
                created_at=datetime.now(timezone.utc),
            )
            results.append(
                BuildResult(
                    event=event_call,
                    validation_errors=[],
                    is_valid=True,
                    idempotency_key=call_idemp,
                )
            )

    # 3. Qualification resolution event
    if qualification_outcome is not None:
        qual_res = build_event(
            qualification_outcome=qualification_outcome,
            lead=lead,
            ad_id=ad_id,
            campaign_name=campaign_name,
            crm_name=crm_name,
            upload_time=now,
            dry_run=dry_run,
        )
        results.append(qual_res)

    return results


def validate_batch(
    events: list[FeedbackEvent],
    upload_time: Optional[datetime] = None,
) -> list[ValidationError]:
    """
    Validate an entire batch of FeedbackEvents against Meta CAPI constraints.

    Meta rule:
    - Maximum 1,000 events per batch request.
    - If any event fails, the batch is discarded (atomic failure).
    """
    errors: list[ValidationError] = []

    if len(events) > CAPI_MAX_BATCH_SIZE:
        errors.append(
            ValidationError(
                field="batch_size",
                message=f"Batch size of {len(events)} exceeds Meta's maximum limit of {CAPI_MAX_BATCH_SIZE} events per batch",
            )
        )

    for idx, event in enumerate(events):
        event_errors = validate_payload(event, upload_time=upload_time)
        for err in event_errors:
            errors.append(
                ValidationError(
                    field=f"events[{idx}].{err.field}",
                    message=f"Event {idx} ({event.idempotency_key}): {err.message}",
                )
            )

    return errors


def chunk_into_batches(
    events: list[FeedbackEvent],
    batch_size: int = CAPI_MAX_BATCH_SIZE,
) -> list[list[FeedbackEvent]]:
    """Partition events into batches conforming to Meta's batch size limit."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    return [events[i : i + batch_size] for i in range(0, len(events), batch_size)]


def validate_payload(
    event: FeedbackEvent,
    upload_time: Optional[datetime] = None,
) -> list[ValidationError]:
    """
    Validate a FeedbackEvent payload against official Meta Conversion Leads requirements.

    Required fields:
        - event_name (non-empty string)
        - event_time (positive Unix timestamp within 7 days of upload)
        - action_source == "system_generated"
        - user_data with unhashed lead_id
        - custom_data containing lead_event_source and event_source="crm"
    """
    errors: list[ValidationError] = []

    if not event.event_name:
        errors.append(ValidationError("event_name", "event_name is required"))

    if event.event_time <= 0:
        errors.append(
            ValidationError("event_time", "event_time must be a positive Unix timestamp")
        )
    else:
        now = upload_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now_ts = now.timestamp()
        if event.event_time > int(now_ts):
            errors.append(ValidationError("event_time", "event_time cannot be in the future"))
        age_days = (now_ts - event.event_time) / 86400.0
        if age_days > CAPI_MAX_UPLOAD_AGE_DAYS:
            errors.append(
                ValidationError(
                    "event_time",
                    f"event_time is {age_days:.1f} days old; Meta CAPI rejects events older than {CAPI_MAX_UPLOAD_AGE_DAYS:.0f} days",
                )
            )

    if event.action_source != CAPI_ACTION_SOURCE:
        errors.append(
            ValidationError(
                "action_source",
                f"action_source must be '{CAPI_ACTION_SOURCE}', got '{event.action_source}'",
            )
        )

    if not event.user_data:
        errors.append(
            ValidationError("user_data", "user_data must contain customer matching parameters")
        )
    else:
        lead_id = event.user_data.get("lead_id")
        if lead_id is not None and not is_valid_lead_id(lead_id):
            errors.append(
                ValidationError(
                    "user_data.lead_id",
                    f"lead_id must be a 15-17 digit numeric string as assigned by Meta. Got: '{lead_id}'",
                )
            )
        has_identifier = bool(
            (lead_id and is_valid_lead_id(lead_id))
            or event.user_data.get("em")
            or event.user_data.get("ph")
        )
        if not has_identifier:
            errors.append(
                ValidationError(
                    "user_data",
                    "user_data must contain at least one valid identifier (lead_id, em, or ph)",
                )
            )

    # Validate custom_data parameters required by Meta Conversion Leads
    if not isinstance(event.custom_data, dict):
        errors.append(ValidationError("custom_data", "custom_data must be a dictionary"))
    else:
        if not event.custom_data.get("lead_event_source"):
            errors.append(
                ValidationError(
                    "custom_data.lead_event_source",
                    "custom_data must include lead_event_source (CRM name)",
                )
            )
        if event.custom_data.get("event_source") != DEFAULT_EVENT_SOURCE:
            errors.append(
                ValidationError(
                    "custom_data.event_source",
                    f"custom_data.event_source must be '{DEFAULT_EVENT_SOURCE}'",
                )
            )

    if not event.idempotency_key:
        errors.append(
            ValidationError("idempotency_key", "idempotency_key is required for deduplication")
        )

    return errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha256_hex(value: str) -> str:
    """SHA-256 hash a string value, returning lowercase hex digest."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _make_idempotency_key(prefix: str, lead_id: str) -> str:
    """
    Deterministic idempotency key from prefix/outcome and lead IDs.
    Same inputs always produce the same key — prevents duplicate events.
    """
    combined = f"{prefix}:{lead_id}"
    return _sha256_hex(combined)[:32]


def _build_user_data_synthetic(lead_id: str) -> dict[str, Any]:
    """
    Build user_data object matching Meta CAPI requirements.

    - `lead_id` MUST be nested inside user_data as an UNHASHED string.
    - Customer identifiers like `em` and `ph` must be SHA-256 hashed lowercase strings.
    """
    synthetic_email_hash = _sha256_hex(f"synthetic_email_{lead_id}")
    synthetic_phone_hash = _sha256_hex(f"synthetic_phone_{lead_id}")

    return {
        "lead_id": str(lead_id),
        "em": synthetic_email_hash,
        "ph": synthetic_phone_hash,
    }
