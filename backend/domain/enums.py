"""Domain enums shared across modules."""

from enum import Enum


class LeadStatus(str, Enum):
    SUBMITTED = "submitted"
    PENDING_CONTACT = "pending_contact"
    CONTACTED = "contacted"
    PENDING_QUALIFICATION = "pending_qualification"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    UNRESOLVED = "unresolved"


class CallOutcome(str, Enum):
    ANSWERED = "answered"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    DISCONNECTED = "disconnected"
    INVALID_NUMBER = "invalid_number"


class QualificationResult(str, Enum):
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"


class DecisionAction(str, Enum):
    COLLECT_MORE_DATA = "collect_more_data"
    CONTINUE_MONITORING = "continue_monitoring"
    INVESTIGATE_LOW_REACHABILITY = "investigate_low_reachability"
    REFRESH_CREATIVE = "refresh_creative"
    CONSIDER_PAUSE = "consider_pause"
    CONSIDER_REALLOCATE = "consider_reallocate"
    SHIFT_SPEND = "shift_spend"
    RAISE_BUDGET = "raise_budget"
    LAUNCH_AD = "launch_ad"
    FLAG_INSUFFICIENT_EVIDENCE = "flag_insufficient_evidence"
    FLAG_ABNORMAL_CHANGE = "flag_abnormal_change"


class DecisionTier(str, Enum):
    GATED = "gated"
    WITHIN_GUARDRAILS = "within_guardrails"
    AUTONOMOUS = "autonomous"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_REQUIRED = "not_required"


class FeedbackValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    SKIPPED = "skipped"


class FeedbackProcessingStatus(str, Enum):
    DRY_RUN = "dry_run"
    SENT = "sent"
    FAILED = "failed"
    DUPLICATE = "duplicate"
