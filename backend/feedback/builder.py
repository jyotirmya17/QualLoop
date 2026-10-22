"""
Meta Conversions API feedback event builder.

Builds and validates event payloads for Meta's Conversions API (Graph API v21.0).
Runs in dry-run mode by default — no HTTP calls are made.

ARCHITECTURE BOUNDARY:
- This module builds payloads. It does not send them.
- A future `transmitter.py` module would handle sending, requiring real credentials.
- The two concerns are intentionally separated.

Reference: https://developers.facebook.com/docs/marketing-api/conversions-api/
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from domain.enums import (
    FeedbackProcessingStatus,
    FeedbackValidationStatus,
    QualificationResult,
)
from domain.models import FeedbackEvent, Lead, QualificationOutcome

logger = structlog.get_logger(__name__)

# Meta CAPI required fields per v21.0 specification
CAPI_EVENT_NAME = "Lead"  # Standard Meta event name for lead qualification
CAPI_ACTION_SOURCE = "crm"  # Events originate from CRM, not website pixel


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


def build_event(
    qualification_outcome: QualificationOutcome,
    lead: Lead,
    ad_id: str,
    campaign_name: str = "",
    dry_run: bool = True,
) -> BuildResult:
    """
    Build a validated Meta CAPI event payload for a qualified lead.

    Args:
        qualification_outcome: The resolved qualification outcome (must be QUALIFIED)
        lead: The lead record
        ad_id: The advertisement ID for custom_data
        campaign_name: Optional campaign name for custom_data
        dry_run: If True, event will be logged but not transmitted (default: True)

    Returns:
        BuildResult with the event (if valid) and any validation errors

    Notes:
        - Only QUALIFIED outcomes should be sent to Meta
        - All PII fields must be SHA-256 hashed
        - In v1 (simulation), all user_data values are synthetic hashes
        - event_time is Unix timestamp of qualification resolution
        - idempotency_key prevents duplicate processing
    """
    idempotency_key = _make_idempotency_key(qualification_outcome.id, lead.id)
    errors: list[ValidationError] = []

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

    # Validate resolved_at is in the past
    now_ts = datetime.now(timezone.utc).timestamp()
    resolved_ts = qualification_outcome.resolved_at
    if resolved_ts.tzinfo is None:
        resolved_ts = resolved_ts.replace(tzinfo=timezone.utc)
    event_time_unix = int(resolved_ts.timestamp())

    if event_time_unix > int(now_ts):
        errors.append(
            ValidationError(
                field="qualification_outcome.resolved_at",
                message="Event time is in the future — timestamps must not be future-dated",
            )
        )

    # Validate event_time is not too old (Meta rejects events older than 7 days)
    age_days = (now_ts - event_time_unix) / 86400
    if age_days > 7.0:
        errors.append(
            ValidationError(
                field="qualification_outcome.resolved_at",
                message=(
                    f"Event is {age_days:.1f} days old. "
                    f"Meta CAPI rejects events older than 7 days."
                ),
            )
        )

    # Build user_data with synthetic hashed values (in production: real hashed PII)
    # In simulation, we use lead_id as a proxy for PII to ensure uniqueness
    user_data = _build_user_data_synthetic(lead.id)

    # Build custom_data
    custom_data: dict[str, Any] = {
        "lead_id": lead.id,
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
        event_name=CAPI_EVENT_NAME,
        event_time=event_time_unix,
        action_source=CAPI_ACTION_SOURCE,
        user_data=user_data,
        custom_data=custom_data,
        validation_status=FeedbackValidationStatus.VALID,
        processing_status=processing_status,
        created_at=datetime.now(timezone.utc),
    )

    if dry_run:
        logger.info(
            "feedback_event_dry_run",
            idempotency_key=idempotency_key,
            event_name=event.event_name,
            event_time=event.event_time,
            ad_id=ad_id,
            note="DRY RUN — payload not transmitted to Meta",
        )

    return BuildResult(
        event=event,
        validation_errors=[],
        is_valid=True,
        idempotency_key=idempotency_key,
    )


def validate_payload(event: FeedbackEvent) -> list[ValidationError]:
    """
    Validate a FeedbackEvent payload against Meta CAPI v21.0 requirements.

    This is a secondary validation gate — `build_event` already validates,
    but this can be called independently for re-validation.

    Required fields per Meta CAPI v21.0:
        - event_name (non-empty string)
        - event_time (positive Unix timestamp)
        - action_source
        - user_data (non-empty dict)
    """
    errors: list[ValidationError] = []

    if not event.event_name:
        errors.append(ValidationError("event_name", "event_name is required"))

    if event.event_time <= 0:
        errors.append(
            ValidationError("event_time", "event_time must be a positive Unix timestamp")
        )

    if not event.action_source:
        errors.append(ValidationError("action_source", "action_source is required"))

    if not event.user_data:
        errors.append(
            ValidationError("user_data", "user_data must contain at least one hashed field")
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


def _make_idempotency_key(outcome_id: str, lead_id: str) -> str:
    """
    Deterministic idempotency key from outcome and lead IDs.
    Same outcome always produces the same key — prevents duplicate events.
    """
    combined = f"{outcome_id}:{lead_id}"
    return _sha256_hex(combined)[:32]  # 32-char prefix is sufficient for dedup


def _build_user_data_synthetic(lead_id: str) -> dict[str, str]:
    """
    Build synthetic user_data for simulation mode.

    In production, this would be replaced with:
        {"em": sha256(normalize(email)), "ph": sha256(normalize(phone)), ...}

    In simulation, we derive synthetic hashes from the lead_id so that:
    - Each lead has a unique but stable synthetic hash
    - No real PII is ever processed
    - The payload structure matches Meta CAPI v21.0 format
    """
    synthetic_email_hash = _sha256_hex(f"synthetic_email_{lead_id}")
    synthetic_phone_hash = _sha256_hex(f"synthetic_phone_{lead_id}")

    return {
        "em": synthetic_email_hash,  # hashed email
        "ph": synthetic_phone_hash,  # hashed phone
        # Note: In production, also include fn (first_name), ln (last_name),
        # ct (city), st (state), zp (zip), country where available
    }
