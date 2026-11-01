"""Tests de la persistance SQLite du suivi post-candidature (OPP-223).

Base SQLite en mémoire : aucune I/O disque, aucun réseau.
"""

import pytest

from app.application_tracking import INTERVIEW, OFFER, REJECTED, create_tracking_event
from app.application_tracking_store import (
    ApplicationTrackingRepository,
    ApplicationTrackingStore,
)
from app.db import connect


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield ApplicationTrackingStore(conn)
    conn.close()


def test_store_satisfies_repository_protocol(store):
    assert isinstance(store, ApplicationTrackingRepository)


def test_append_then_history_roundtrip(store):
    event = create_tracking_event(
        INTERVIEW, event_date="2026-11-15", comment="Visio", now=lambda: "t1"
    )

    store.append("cand-1:off-1", "cand-1", event)

    assert store.history("cand-1:off-1") == (event,)


def test_history_is_in_insertion_order(store):
    firstInterview = create_tracking_event(INTERVIEW, now=lambda: "t1")
    secondInterview = create_tracking_event(INTERVIEW, now=lambda: "t2")
    rejection = create_tracking_event(REJECTED, now=lambda: "t3")

    store.append("cand-1:off-1", "cand-1", firstInterview)
    store.append("cand-1:off-1", "cand-1", secondInterview)
    store.append("cand-1:off-1", "cand-1", rejection)

    assert store.history("cand-1:off-1") == (firstInterview, secondInterview, rejection)


def test_history_is_isolated_per_recommendation(store):
    onOfferOne = create_tracking_event(INTERVIEW, now=lambda: "t1")
    onOfferTwo = create_tracking_event(OFFER, now=lambda: "t2")

    store.append("cand-1:off-1", "cand-1", onOfferOne)
    store.append("cand-1:off-2", "cand-1", onOfferTwo)

    assert store.history("cand-1:off-1") == (onOfferOne,)
    assert store.history("cand-1:off-2") == (onOfferTwo,)


def test_history_of_unknown_recommendation_is_empty(store):
    assert store.history("nope") == ()


def test_events_for_groups_several_recommendations_in_one_read(store):
    onOfferOne = create_tracking_event(INTERVIEW, now=lambda: "t1")
    rejectionOnOne = create_tracking_event(REJECTED, now=lambda: "t2")
    onOfferTwo = create_tracking_event(OFFER, now=lambda: "t3")
    store.append("cand-1:off-1", "cand-1", onOfferOne)
    store.append("cand-1:off-1", "cand-1", rejectionOnOne)
    store.append("cand-1:off-2", "cand-1", onOfferTwo)

    grouped = store.events_for(["cand-1:off-1", "cand-1:off-2", "cand-1:off-3"])

    assert grouped == {
        "cand-1:off-1": (onOfferOne, rejectionOnOne),
        "cand-1:off-2": (onOfferTwo,),
    }


def test_events_for_empty_list_is_empty(store):
    assert store.events_for([]) == {}
