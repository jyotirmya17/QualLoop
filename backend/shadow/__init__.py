"""
Shadow Evaluation Foundation package for QualLoop.

Provides versioned schemas, sink interfaces, and an isolated offline runner for
shadow-mode economic decision evaluation without connecting to live client campaigns
or external ad mutation platforms.
"""

from backend.shadow.contracts import (
    BusinessAssumptionStatus,
    DecisionTimeSnapshot,
    ShadowAction,
    ShadowBusinessAssumptions,
    ShadowEconomicDecision,
    ShadowEconomicDecisionLoggedEvent,
)
from backend.shadow.sink import InMemoryShadowEventSink, ShadowEventSink
from backend.shadow.runner import execute_shadow_evaluation

__all__ = [
    "BusinessAssumptionStatus",
    "DecisionTimeSnapshot",
    "InMemoryShadowEventSink",
    "ShadowAction",
    "ShadowBusinessAssumptions",
    "ShadowEconomicDecision",
    "ShadowEconomicDecisionLoggedEvent",
    "ShadowEventSink",
    "execute_shadow_evaluation",
]
