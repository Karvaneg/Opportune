"""Tests du suivi post-candidature de l'API Hermes (OPP-223).

Ajout et lecture d'événements de suivi sur ``HermesApi.dispatch`` (aucun réseau, vrais
dépôts SQLite en mémoire, mode ouvert sans auth). On vérifie la garde « déclarée candidatée »
(409 sinon), le type d'événement invalide (400), la répétabilité de l'entretien, l'exposition
de l'historique dans le détail de la reco, et le non-montage des routes sans service câblé.
"""

import itertools

import pytest

from api.app import HermesApi
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.application_tracking import INTERVIEW, OFFER, REJECTED
from app.application_tracking_service import ApplicationTrackingService
from app.application_tracking_store import ApplicationTrackingStore
from app.candidate_profile import create_profile
from app.db import connect
from app.decision import decision_id
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _offer(**overrides) -> Offer:
    data = dict(
        id="off-app", title="App", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


_RID = decision_id("cand-1", "off-app")


@pytest.fixture
def env():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    applications = ApplicationActionStore(conn)
    tracking_store = ApplicationTrackingStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    offers.save(_offer())
    decisions = DecisionService(DecisionStore(conn), now=lambda: "2026-09-04T00:00:00+00:00")
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        decisions,
        runs=RunStore(conn),
        run_id=lambda: "run-1",
        now=lambda: "2026-09-04T12:00:00+00:00",
    )
    ids = (str(n) for n in itertools.count(1))
    actions = ActionService(
        decisions, applications, OutboundMessageActionStore(conn),
        new_id=lambda: next(ids), now=lambda: "2026-09-05T00:00:00+00:00",
    )
    tracking = ApplicationTrackingService(
        applications, tracking_store, now=lambda: "2026-09-06T00:00:00+00:00"
    )
    api = HermesApi(orchestrator, actions, tracking=tracking)
    api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    yield api, orchestrator
    conn.close()


def _applied(api):
    """Amène la candidature jusqu'à l'état « déclarée candidatée » (préalable au suivi)."""
    api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"})
    api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    api.dispatch("POST", f"/applications/{_RID}/applied", None)


# --- Ajout d'un événement : garde « déclarée candidatée » --------------------

def test_add_event_without_declared_application_is_409(env):
    api, _ = env

    resp = api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": INTERVIEW})

    assert resp.status == 409


def test_add_event_on_intention_not_yet_applied_is_409(env):
    api, _ = env
    api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"})
    api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})

    resp = api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": INTERVIEW})

    assert resp.status == 409


def test_add_event_after_applied_returns_201_with_history(env):
    api, _ = env
    _applied(api)

    resp = api.dispatch(
        "POST", f"/applications/{_RID}/tracking",
        {"kind": INTERVIEW, "event_date": "2026-11-15", "comment": "Visio RH"},
    )

    assert resp.status == 201
    assert resp.body["events"] == [
        {"kind": INTERVIEW, "at": "2026-09-06T00:00:00+00:00",
         "event_date": "2026-11-15", "comment": "Visio RH"}
    ]


# --- Type d'événement et date ------------------------------------------------

def test_add_event_missing_kind_is_400(env):
    api, _ = env
    _applied(api)

    resp = api.dispatch("POST", f"/applications/{_RID}/tracking", {"comment": "x"})

    assert resp.status == 400
    assert "kind" in resp.body["error"]


def test_add_event_unknown_kind_is_400(env):
    api, _ = env
    _applied(api)

    resp = api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": "embauché"})

    assert resp.status == 400


def test_interview_event_date_may_be_in_the_future(env):
    api, _ = env
    _applied(api)

    resp = api.dispatch(
        "POST", f"/applications/{_RID}/tracking",
        {"kind": INTERVIEW, "event_date": "2099-01-01"},
    )

    assert resp.status == 201


@pytest.mark.parametrize("bad", ["pas une date", "2026-13-40", 20261115])
def test_add_event_rejects_invalid_event_date(env, bad):
    api, _ = env
    _applied(api)

    resp = api.dispatch(
        "POST", f"/applications/{_RID}/tracking", {"kind": INTERVIEW, "event_date": bad}
    )

    assert resp.status == 400
    assert "event_date" in resp.body["error"]


# --- Historique : répétable, ordonné, lisible --------------------------------

def test_interview_is_repeatable_and_history_is_ordered(env):
    api, _ = env
    _applied(api)

    api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": INTERVIEW})
    api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": INTERVIEW})
    api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": REJECTED})
    history = api.dispatch("GET", f"/applications/{_RID}/tracking", None)

    assert history.status == 200
    assert [e["kind"] for e in history.body["events"]] == [INTERVIEW, INTERVIEW, REJECTED]


def test_get_tracking_is_empty_before_any_event(env):
    api, _ = env
    _applied(api)

    resp = api.dispatch("GET", f"/applications/{_RID}/tracking", None)

    assert resp.status == 200
    assert resp.body["events"] == []


# --- Exposition dans le détail de la recommandation --------------------------

def test_recommendation_detail_exposes_tracking_history(env):
    api, _ = env
    _applied(api)
    api.dispatch("POST", f"/applications/{_RID}/tracking", {"kind": OFFER})

    resp = api.dispatch("GET", f"/recommendations/{_RID}", None)

    assert resp.status == 200
    assert [e["kind"] for e in resp.body["application"]["tracking"]] == [OFFER]


# --- Méthode et montage ------------------------------------------------------

def test_tracking_wrong_method_is_405(env):
    api, _ = env

    resp = api.dispatch("PUT", f"/applications/{_RID}/tracking", None)

    assert resp.status == 405


def test_tracking_routes_absent_without_service(env):
    _, orchestrator = env

    api_without_tracking = HermesApi(orchestrator)
    resp = api_without_tracking.dispatch("GET", f"/applications/{_RID}/tracking", None)

    assert resp.status == 404
