"""Tests du domaine pur du suivi post-candidature (OPP-223).

Logique pure : aucune I/O, aucun réseau, horloge injectée.
"""

import pytest

from app.application_tracking import (
    INTERVIEW,
    OFFER,
    REJECTED,
    TrackingError,
    create_tracking_event,
)


def test_create_event_is_stamped_with_the_injected_clock():
    clock = lambda: "2026-11-02T10:00:00+00:00"

    event = create_tracking_event(INTERVIEW, now=clock)

    assert event.kind == INTERVIEW
    assert event.at == "2026-11-02T10:00:00+00:00"


def test_create_event_carries_event_date_and_comment():
    interviewDate = "2026-11-15"

    event = create_tracking_event(
        INTERVIEW, event_date=interviewDate, comment="Visio avec la RH", now=lambda: "t0"
    )

    assert event.event_date == interviewDate
    assert event.comment == "Visio avec la RH"


def test_event_date_and_comment_default_to_none():
    event = create_tracking_event(REJECTED, now=lambda: "t0")

    assert event.event_date is None
    assert event.comment is None


def test_unknown_kind_is_rejected():
    with pytest.raises(TrackingError):
        create_tracking_event("embauché", now=lambda: "t0")


def test_event_date_is_rejected_for_a_non_interview_kind():
    with pytest.raises(TrackingError):
        create_tracking_event(REJECTED, event_date="2026-11-15", now=lambda: "t0")


def test_offer_is_an_accepted_kind():
    event = create_tracking_event(OFFER, now=lambda: "t0")

    assert event.kind == OFFER
