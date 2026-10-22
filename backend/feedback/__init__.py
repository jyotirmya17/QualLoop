"""Feedback package."""

from feedback.builder import (
    BuildResult,
    FitCheckResult,
    ValidationError,
    build_event,
    build_lead_history_events,
    check_business_fit,
    chunk_into_batches,
    validate_batch,
    validate_payload,
)

__all__ = [
    "build_event",
    "build_lead_history_events",
    "validate_payload",
    "validate_batch",
    "chunk_into_batches",
    "check_business_fit",
    "BuildResult",
    "FitCheckResult",
    "ValidationError",
]
