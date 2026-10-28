"""
Isolated sink interfaces for QualLoop shadow-mode event telemetry.

Keeps shadow telemetry strictly decoupled from the production audit trail
(`backend.audit.trail`), ensuring that shadow recommendations cannot leak into
production audit compliance reports or client-facing dashboards.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import uuid

from backend.shadow.contracts import ShadowEconomicDecisionLoggedEvent


class ShadowEventSink(ABC):
    """Abstract interface for recording and querying shadow events."""

    @abstractmethod
    def record_event(self, event: ShadowEconomicDecisionLoggedEvent) -> bool:
        """
        Record a shadow event idempotently.
        Returns True if the event was newly recorded, False if deduplicated.
        """
        pass

    @abstractmethod
    def get_event(self, event_id: uuid.UUID) -> Optional[ShadowEconomicDecisionLoggedEvent]:
        """Fetch a specific shadow event by its unique UUID."""
        pass

    @abstractmethod
    def query_events(
        self,
        advertisement_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ShadowEconomicDecisionLoggedEvent]:
        """Query stored shadow events matching optional criteria."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear store (testing and offline replay only)."""
        pass


class InMemoryShadowEventSink(ShadowEventSink):
    """
    Isolated in-memory implementation of ShadowEventSink.
    Enforces idempotency using a composite key:
    `idempotency_key = (advertisement_id, computed_at_iso, evaluator_version)`
    """

    def __init__(self) -> None:
        self._events_by_id: Dict[uuid.UUID, ShadowEconomicDecisionLoggedEvent] = {}
        self._idempotency_index: Dict[str, uuid.UUID] = {}

    def _compute_idempotency_key(self, event: ShadowEconomicDecisionLoggedEvent) -> str:
        computed_at_iso = event.decision_time_snapshot.computed_at.isoformat()
        return f"{event.advertisement_id}:{computed_at_iso}:{event.evaluator_version}"

    def record_event(self, event: ShadowEconomicDecisionLoggedEvent) -> bool:
        key = self._compute_idempotency_key(event)
        if key in self._idempotency_index:
            # Idempotent skip — duplicate snapshot evaluation
            return False

        self._idempotency_index[key] = event.event_id
        self._events_by_id[event.event_id] = event
        return True

    def get_event(self, event_id: uuid.UUID) -> Optional[ShadowEconomicDecisionLoggedEvent]:
        return self._events_by_id.get(event_id)

    def query_events(
        self,
        advertisement_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ShadowEconomicDecisionLoggedEvent]:
        results = []
        for event in self._events_by_id.values():
            if advertisement_id is not None and event.advertisement_id != advertisement_id:
                continue
            if campaign_id is not None and event.campaign_id != campaign_id:
                continue
            results.append(event)
            if len(results) >= limit:
                break
        return results

    def clear(self) -> None:
        self._events_by_id.clear()
        self._idempotency_index.clear()
