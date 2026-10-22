"""
Maturity window logic for the QualLoop estimator.

A lead or contact is "mature" when enough time has elapsed for its
outcome to plausibly be resolved. Immature leads must not contribute
to the estimation denominator.

See docs/STATISTICAL_MODEL.md §2 for full specification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from domain.enums import CallOutcome, QualificationResult
from domain.models import CallAttempt, Lead, QualificationOutcome


class MaturityObservations(NamedTuple):
    """
    Structured counts for estimator input.

    reachability:
        n_mature_leads: leads past contact_maturity_days window
        k_contacted: leads who were successfully contacted

    qualification:
        n_mature_contacts: contacts past qualification_maturity_days with resolved outcomes
        k_qualified: among those, how many qualified

    Other:
        n_leads: total leads (for maturity fraction computation)
        n_contacts: total successfully contacted leads
        n_pending_contact: leads inside contact maturity window
        n_pending_qualification: contacts inside qualification maturity window
    """

    n_leads: int
    n_mature_leads: int
    k_contacted: int
    n_contacts: int
    n_mature_contacts: int
    k_qualified: int
    n_pending_contact: int
    n_pending_qualification: int


def compute_maturity_observations(
    leads: list[Lead],
    call_attempts: list[CallAttempt],
    qualification_outcomes: list[QualificationOutcome],
    observation_time: datetime,
    contact_maturity_days: float = 3.0,
    qualification_maturity_days: float = 7.0,
) -> MaturityObservations:
    """
    Compute observation counts respecting maturity windows.

    Args:
        leads: All leads for the target ad
        call_attempts: All call attempts for those leads
        qualification_outcomes: All qualification outcomes for those leads
        observation_time: The reference "now" — leads created before this time are considered
        contact_maturity_days: Days after creation for a lead to be mature for reachability
        qualification_maturity_days: Days after first contact for a contact to be mature

    Returns:
        MaturityObservations with correct denominators

    Rules enforced:
        - Pending leads (inside contact window) are NOT counted in reachability denominator
        - Pending contacts (inside qualification window) are NOT counted in intent denominator
        - Unreachable leads inform reachability but never intent denominator
        - Only resolved contacts (qualified OR disqualified) count in intent denominator
    """
    if observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=timezone.utc)

    # Index call attempts and qualification outcomes by lead_id
    calls_by_lead: dict[str, list[CallAttempt]] = {}
    for ca in call_attempts:
        calls_by_lead.setdefault(ca.lead_id, []).append(ca)

    quals_by_lead: dict[str, QualificationOutcome] = {}
    for qo in qualification_outcomes:
        quals_by_lead[qo.lead_id] = qo

    n_leads = len(leads)
    n_mature_leads = 0
    k_contacted = 0
    n_contacts = 0
    n_mature_contacts = 0
    k_qualified = 0
    n_pending_contact = 0
    n_pending_qualification = 0

    for lead in leads:
        lead_created = lead.created_at
        if lead_created.tzinfo is None:
            lead_created = lead_created.replace(tzinfo=timezone.utc)

        lead_age_days = (observation_time - lead_created).total_seconds() / 86400.0

        # Determine if lead has been successfully contacted
        lead_calls = calls_by_lead.get(lead.id, [])
        contact_attempt = _find_successful_contact(lead_calls)
        was_contacted = contact_attempt is not None

        if lead_age_days >= contact_maturity_days:
            # Lead is mature for reachability analysis
            n_mature_leads += 1
            if was_contacted:
                k_contacted += 1
                n_contacts += 1
        else:
            # Lead is still pending contact
            n_pending_contact += 1
            if was_contacted:
                # Contacted early (before maturity window) — still count as contact
                # but NOT in reachability denominator (lead not yet mature)
                n_contacts += 1

        # Qualification analysis — only for contacted leads
        if was_contacted and contact_attempt is not None:
            contact_time = contact_attempt.attempted_at
            if contact_time.tzinfo is None:
                contact_time = contact_time.replace(tzinfo=timezone.utc)

            contact_age_days = (observation_time - contact_time).total_seconds() / 86400.0

            qual = quals_by_lead.get(lead.id)

            if qual is not None:
                # Qualification has been resolved
                if contact_age_days >= qualification_maturity_days:
                    n_mature_contacts += 1
                    if qual.result == QualificationResult.QUALIFIED:
                        k_qualified += 1
                else:
                    # Resolved but contact is not yet mature — do not count
                    n_pending_qualification += 1
            else:
                # No qualification outcome yet
                if contact_age_days >= qualification_maturity_days:
                    # Mature contact with no resolution — treat as unresolved, not disqualified
                    # Per spec: unresolved is NOT a failure
                    pass  # excluded from denominator
                else:
                    n_pending_qualification += 1

    return MaturityObservations(
        n_leads=n_leads,
        n_mature_leads=n_mature_leads,
        k_contacted=k_contacted,
        n_contacts=n_contacts,
        n_mature_contacts=n_mature_contacts,
        k_qualified=k_qualified,
        n_pending_contact=n_pending_contact,
        n_pending_qualification=n_pending_qualification,
    )


def _find_successful_contact(calls: list[CallAttempt]) -> CallAttempt | None:
    """Return the first successful (ANSWERED) call attempt, or None."""
    for ca in sorted(calls, key=lambda c: c.attempted_at):
        if ca.outcome == CallOutcome.ANSWERED:
            return ca
    return None
