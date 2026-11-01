"""Tests du service de suivi post-candidature (OPP-223).

Stores SQLite réels en mémoire partageant une connexion : aucune I/O disque, aucun réseau.
"""

import pytest

from app.action import SIMULATED, ApplicationAction
from app.action_store import ApplicationActionStore
from app.application_tracking import INTERVIEW, TrackingError
from app.application_tracking_service import (
    ApplicationTrackingService,
    TrackingNotAllowedError,
)
from app.application_tracking_store import ApplicationTrackingStore
from app.db import connect


def _application(recommendation_id="cand-1:off-1", *, applied_at):
    return ApplicationAction(
        action_id=f"app_{recommendation_id}",
        recommendation_id=recommendation_id,
        candidate_id="cand-1",
        decision_status_at_confirmation="approved",
        confirmed_at="t0",
        created_at="t0",
        status=SIMULATED,
        applied_at=applied_at,
    )


@pytest.fixture
def context():
    conn = connect(":memory:")
    applications = ApplicationActionStore(conn)
    tracking = ApplicationTrackingStore(conn)
    service = ApplicationTrackingService(applications, tracking, now=lambda: "t1")
    yield service, applications
    conn.close()


def test_add_event_on_a_declared_application_appends_to_history(context):
    service, applications = context
    applications.save(_application(applied_at="2026-10-01"))

    event = service.add_event(
        "cand-1:off-1", INTERVIEW, event_date="2026-11-15", comment="Visio"
    )

    assert event.kind == INTERVIEW
    assert event.at == "t1"
    assert service.history("cand-1:off-1") == (event,)


def test_add_event_without_an_application_is_refused(context):
    service, _ = context

    with pytest.raises(TrackingNotAllowedError):
        service.add_event("cand-1:off-1", INTERVIEW)


def test_add_event_on_a_not_yet_applied_intention_is_refused(context):
    service, applications = context
    applications.save(_application(applied_at=None))

    with pytest.raises(TrackingNotAllowedError):
        service.add_event("cand-1:off-1", INTERVIEW)


def test_add_event_with_an_unknown_kind_is_refused(context):
    service, applications = context
    applications.save(_application(applied_at="2026-10-01"))

    with pytest.raises(TrackingError):
        service.add_event("cand-1:off-1", "embauché")


def test_invalid_kind_is_a_400_even_before_the_applied_guard(context):
    # Payload invalide (kind inconnu) sur une candidature non déclarée : la validation de forme
    # (TrackingError → 400) prime sur la garde d'état (TrackingNotAllowedError → 409).
    service, _ = context

    with pytest.raises(TrackingError):
        service.add_event("cand-1:off-1", "embauché")


def test_history_of_a_recommendation_without_events_is_empty(context):
    service, applications = context
    applications.save(_application(applied_at="2026-10-01"))

    assert service.history("cand-1:off-1") == ()


def test_history_for_reads_several_recommendations_in_one_batch(context):
    service, applications = context
    applications.save(_application("cand-1:off-1", applied_at="2026-10-01"))
    applications.save(_application("cand-1:off-2", applied_at="2026-10-01"))
    firstEvent = service.add_event("cand-1:off-1", INTERVIEW)

    grouped = service.history_for(["cand-1:off-1", "cand-1:off-2"])

    assert grouped == {"cand-1:off-1": (firstEvent,)}
