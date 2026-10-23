"""
Naive baseline policy implementation.

This policy reflects common, naive advertising heuristics without statistical rigor:
1. Denominator: Counts all leads regardless of maturity (does not wait for maturity window).
2. Reachability estimate: k_contacted / n_total (raw proportion including pending leads).
3. Qualification estimate: k_qualified / max(k_contacted, 1) — treats 0 contacts as 1.
4. Pending leads: Counted in the denominator as non-conversions.
5. Unreachable leads: Counted against qualification rate.
6. Decision rule: If observed qualification rate < pause_threshold (default 0.10) -> consider_pause;
   otherwise continue_monitoring.
7. No credible intervals or uncertainty representation.
8. No cooldown period.
9. No maturity gating.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from domain.enums import CallOutcome, DecisionAction, QualificationResult
from domain.models import Advertisement, CallAttempt, Lead, QualificationOutcome


@dataclass
class BaselineDecision:
    """Decision output from the naive baseline policy."""

    advertisement_id: str
    action: DecisionAction
    observed_reachability: float
    observed_qualification: float
    n_leads: int
    n_contacts: int
    k_qualified: int
    reason: str


class BaselinePolicy:
    """Naive heuristic policy without uncertainty or maturity modeling."""

    def __init__(self, pause_threshold: float = 0.10):
        self.pause_threshold = pause_threshold

    def evaluate(
        self,
        advertisement: Advertisement,
        leads: list[Lead],
        call_attempts: list[CallAttempt],
        qualification_outcomes: list[QualificationOutcome],
    ) -> BaselineDecision:
        n_leads = len(leads)
        if n_leads == 0:
            return BaselineDecision(
                advertisement_id=advertisement.id,
                action=DecisionAction.CONTINUE_MONITORING,
                observed_reachability=0.0,
                observed_qualification=0.0,
                n_leads=0,
                n_contacts=0,
                k_qualified=0,
                reason="Baseline: No leads observed yet, continue monitoring",
            )

        # Naive contact count: any lead with an answered call
        contacted_lead_ids = {
            ca.lead_id for ca in call_attempts if ca.outcome == CallOutcome.ANSWERED
        }
        n_contacts = len(contacted_lead_ids)

        # Raw reachability: contacted / all leads (including immature)
        observed_reachability = n_contacts / n_leads

        # Naive qualified count
        qualified_lead_ids = {
            qo.lead_id
            for qo in qualification_outcomes
            if qo.result == QualificationResult.QUALIFIED
        }
        k_qualified = len(qualified_lead_ids)

        # Naive qualification rate: k_qualified / max(n_contacts, 1)
        # Note: If 0 contacts, treated as 0% qualification
        denominator = max(n_contacts, 1) if n_contacts > 0 else 1
        observed_qualification = (
            (k_qualified / denominator) if n_contacts > 0 else 0.0
        )

        # Naive threshold check: if observed_qualification < 10%, pause
        if observed_qualification < self.pause_threshold:
            action = DecisionAction.CONSIDER_PAUSE
            reason = (
                f"Baseline: Observed qualification rate {observed_qualification:.1%} "
                f"below threshold {self.pause_threshold:.1%}"
            )
        else:
            action = DecisionAction.CONTINUE_MONITORING
            reason = (
                f"Baseline: Observed qualification rate {observed_qualification:.1%} "
                f"meets or exceeds threshold {self.pause_threshold:.1%}"
            )

        return BaselineDecision(
            advertisement_id=advertisement.id,
            action=action,
            observed_reachability=observed_reachability,
            observed_qualification=observed_qualification,
            n_leads=n_leads,
            n_contacts=n_contacts,
            k_qualified=k_qualified,
            reason=reason,
        )


class BaselineCPolicy:
    """
    Baseline C: Maturity-Aware Naive Policy.

    Characteristics:
    - Same checkpoints (days 3, 7, 14, 21).
    - Mature leads only (lead age >= qualification_maturity_days, e.g. 7 days).
    - Pending leads are excluded (never treated as failures).
    - Unreached leads are kept separate from unqualified leads.
    - Uses point estimate of qualification: q_hat = k_qualified / n_contacts.
    - Pauses only when n_contacts >= min_contacts (default: 12) AND q_hat < pause_threshold (default: 0.15).
    - Crucially: NO Bayesian credible intervals, NO shrinkage (empirical-Bayes pooling).
    """

    def __init__(
        self,
        pause_threshold: float = 0.15,
        min_contacts: int = 12,
        qualification_maturity_days: float = 7.0,
    ):
        self.pause_threshold = pause_threshold
        self.min_contacts = min_contacts
        self.qualification_maturity_days = qualification_maturity_days

    def evaluate(
        self,
        advertisement: Advertisement,
        leads: list[Lead],
        call_attempts: list[CallAttempt],
        qualification_outcomes: list[QualificationOutcome],
        observation_time: datetime,
    ) -> BaselineDecision:
        if observation_time.tzinfo is None:
            observation_time = observation_time.replace(tzinfo=timezone.utc)

        # 1. Filter for mature leads only
        cutoff = observation_time - timedelta(days=self.qualification_maturity_days)
        mature_leads = [l for l in leads if l.created_at <= cutoff]
        mature_lead_ids = {l.id for l in mature_leads}

        if not mature_lead_ids:
            return BaselineDecision(
                advertisement_id=advertisement.id,
                action=DecisionAction.CONTINUE_MONITORING,
                observed_reachability=0.0,
                observed_qualification=0.0,
                n_leads=0,
                n_contacts=0,
                k_qualified=0,
                reason="Baseline C: No mature leads observed yet, continue monitoring",
            )

        # 2. Contacted mature leads
        calls_mature = [ca for ca in call_attempts if ca.lead_id in mature_lead_ids]
        contacted_mature_ids = {
            ca.lead_id for ca in calls_mature if ca.outcome == CallOutcome.ANSWERED
        }
        n_contacts = len(contacted_mature_ids)
        observed_reachability = n_contacts / len(mature_lead_ids)

        # 3. Qualified mature leads
        quals_mature = [
            qo for qo in qualification_outcomes
            if qo.lead_id in contacted_mature_ids and qo.result == QualificationResult.QUALIFIED
        ]
        k_qualified = len(quals_mature)

        # 4. Point estimate evaluation
        if n_contacts < self.min_contacts:
            return BaselineDecision(
                advertisement_id=advertisement.id,
                action=DecisionAction.CONTINUE_MONITORING,
                observed_reachability=observed_reachability,
                observed_qualification=(k_qualified / n_contacts) if n_contacts > 0 else 0.0,
                n_leads=len(mature_leads),
                n_contacts=n_contacts,
                k_qualified=k_qualified,
                reason=f"Baseline C: Insufficient mature contacts ({n_contacts} < {self.min_contacts}), continue monitoring",
            )

        observed_qualification = k_qualified / n_contacts
        if observed_qualification < self.pause_threshold:
            action = DecisionAction.CONSIDER_PAUSE
            reason = (
                f"Baseline C: Observed qualification rate {observed_qualification:.1%} "
                f"({k_qualified}/{n_contacts}) below hurdle threshold {self.pause_threshold:.1%}"
            )
        else:
            action = DecisionAction.CONTINUE_MONITORING
            reason = (
                f"Baseline C: Observed qualification rate {observed_qualification:.1%} "
                f"({k_qualified}/{n_contacts}) meets or exceeds hurdle threshold {self.pause_threshold:.1%}"
            )

        return BaselineDecision(
            advertisement_id=advertisement.id,
            action=action,
            observed_reachability=observed_reachability,
            observed_qualification=observed_qualification,
            n_leads=len(mature_leads),
            n_contacts=n_contacts,
            k_qualified=k_qualified,
            reason=reason,
        )

