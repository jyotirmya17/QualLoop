"""SQLAlchemy ORM models for durable audit persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from domain.enums import ApprovalStatus, DecisionAction
from domain.models import AuditEvent, Decision


class Base(DeclarativeBase):
    pass


class DecisionModel(Base):
    """Authoritative storage for advertising decisions."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    simulation_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    advertisement_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    estimate_snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="autonomous")
    auto_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_required")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    audit_events: Mapped[list[AuditEventModel]] = relationship(
        "AuditEventModel",
        back_populates="decision",
        passive_deletes=True,
        order_by="AuditEventModel.created_at.desc(), AuditEventModel.id.desc()",
    )

    __table_args__ = (
        Index("ix_decisions_created_at_id", "created_at", "id"),
        UniqueConstraint(
            "simulation_run_id",
            "advertisement_id",
            "policy_version",
            name="uq_decisions_run_ad_policy",
        ),
    )

    def to_domain(self) -> Decision:
        created = self.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        return Decision(
            id=self.id,
            simulation_run_id=self.simulation_run_id,
            advertisement_id=self.advertisement_id,
            estimate_snapshot_id=self.estimate_snapshot_id,
            policy_version=self.policy_version,
            action=DecisionAction(self.action),
            reason=self.reason,
            supporting_metrics=self.supporting_metrics or {},
            confidence_level=self.confidence_level,
            tier=self.tier,
            auto_applied=self.auto_applied,
            requires_human_approval=self.requires_human_approval,
            approval_status=ApprovalStatus(self.approval_status),
            created_at=created,
            is_persisted=True,
        )

    @classmethod
    def from_domain(cls, decision: Decision) -> DecisionModel:
        action_val = decision.action.value if hasattr(decision.action, "value") else str(decision.action)
        status_val = (
            decision.approval_status.value
            if hasattr(decision.approval_status, "value")
            else str(decision.approval_status)
        )
        return cls(
            id=decision.id,
            simulation_run_id=decision.simulation_run_id,
            advertisement_id=decision.advertisement_id,
            estimate_snapshot_id=decision.estimate_snapshot_id,
            policy_version=decision.policy_version,
            action=action_val,
            reason=decision.reason,
            supporting_metrics=decision.supporting_metrics or {},
            confidence_level=decision.confidence_level,
            tier=decision.tier,
            auto_applied=decision.auto_applied,
            requires_human_approval=decision.requires_human_approval,
            approval_status=status_val,
            created_at=decision.created_at,
        )


class AuditEventModel(Base):
    """Authoritative storage for audit log events."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    decision_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("decisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    decision: Mapped[Optional[DecisionModel]] = relationship(
        "DecisionModel",
        back_populates="audit_events",
    )

    __table_args__ = (
        Index("ix_audit_events_created_at_id", "created_at", "id"),
    )

    def to_domain(self) -> AuditEvent:
        created = self.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        return AuditEvent(
            id=self.id,
            decision_id=self.decision_id,
            event_type=self.event_type,
            data=self.data or {},
            created_at=created,
        )

    @classmethod
    def from_domain(cls, event: AuditEvent) -> AuditEventModel:
        return cls(
            id=event.id,
            decision_id=event.decision_id,
            event_type=event.event_type,
            data=event.data or {},
            created_at=event.created_at,
        )
