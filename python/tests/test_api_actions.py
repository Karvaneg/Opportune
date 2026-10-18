"""Tests des actions sensibles de l'API Hermes (OPP-096).

Confirmation explicite de candidature/message sur ``HermesApi.dispatch`` (aucun réseau,
vrais dépôts SQLite en mémoire). On vérifie la garde ``confirm: true``, l'exigence d'une
décision ``approved`` pour candidater (409 sinon), la cible inconnue d'un message (404),
l'idempotence par cible, et le non-montage des routes quand le service n'est pas fourni.
"""

import itertools

import pytest

from api.app import HermesApi
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
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
    decisions_store = DecisionStore(conn)
    runs = RunStore(conn)
    applications = ApplicationActionStore(conn)
    messages = OutboundMessageActionStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    offers.save(_offer())
    decisions = DecisionService(decisions_store, now=lambda: "2026-09-04T00:00:00+00:00")
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        decisions,
        runs=runs,
        run_id=lambda: "run-1",
        now=lambda: "2026-09-04T12:00:00+00:00",
    )
    ids = (str(n) for n in itertools.count(1))
    actions = ActionService(
        decisions, applications, messages,
        new_id=lambda: next(ids), now=lambda: "2026-09-05T00:00:00+00:00",
    )
    api = HermesApi(orchestrator, actions)
    # Crée le run "run-1" et la décision pending de off-app.
    api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    yield api, applications, messages, orchestrator
    conn.close()


def _approve(api):
    api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"})


# --- Candidature : garde confirm + garde approved ----------------------------

@pytest.mark.parametrize("bad_body", [{}, {"confirm": False}, {"confirm": "true"}, {"confirm": 1}])
def test_confirm_application_requires_confirm_true(env, bad_body):
    api, applications, _, _ = env
    _approve(api)  # décision OK : c'est bien la garde confirm qui doit trancher
    resp = api.dispatch("POST", f"/applications/{_RID}/confirm", bad_body)
    assert resp.status == 400
    assert "confirm" in resp.body["error"]
    assert applications.count() == 0  # rien confirmé


def test_confirm_application_requires_approved_decision(env):
    api, applications, _, _ = env
    # Décision encore pending → 409.
    resp = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert resp.status == 409
    assert "approved" in resp.body["error"]
    assert applications.count() == 0


def test_confirm_application_absent_decision_is_409(env):
    api, _, _, _ = env
    ghost = decision_id("cand-1", "ghost")
    resp = api.dispatch("POST", f"/applications/{ghost}/confirm", {"confirm": True})
    assert resp.status == 409  # absence de décision → 409 (pas 404), côté candidature


def test_confirm_application_rejected_decision_is_409(env):
    api, applications, _, _ = env
    api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "reject"})
    resp = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert resp.status == 409
    assert applications.count() == 0


def test_confirm_application_success_then_idempotent(env):
    api, applications, _, _ = env
    _approve(api)

    first = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert first.status == 200
    assert first.body == {"action_id": "app_1", "status": "simulated", "already_confirmed": False}
    assert applications.count() == 1

    # Seconde confirmation : même action, aucune nouvelle création/exécution.
    second = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert second.status == 200
    assert second.body == {"action_id": "app_1", "status": "simulated", "already_confirmed": True}
    assert applications.count() == 1


def test_confirm_application_stays_idempotent_after_decision_changes(env):
    api, applications, _, _ = env
    _approve(api)

    first = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert first.status == 200
    assert applications.count() == 1

    # La décision repasse en rejected APRÈS confirmation : l'action reste enregistrée,
    # une re-soumission doit rester idempotente (200) et non renvoyer 409.
    api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "reject"})
    again = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert again.status == 200
    assert again.body == {"action_id": "app_1", "status": "simulated", "already_confirmed": True}
    assert applications.count() == 1


# --- Lecture de l'intention dans le détail de la recommandation --------------

def test_recommendation_detail_exposes_noted_intent(env):
    api, _, _, _ = env
    _approve(api)
    api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})

    resp = api.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp.status == 200
    assert resp.body["application"] == {
        "confirmed": True,
        "confirmed_at": "2026-09-05T00:00:00+00:00",
        "status": "simulated",
        "applied": False,
        "applied_at": None,
    }


def test_recommendation_detail_application_is_none_without_intent(env):
    api, _, _, _ = env
    _approve(api)  # décision approuvée mais AUCUNE intention notée

    resp = api.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp.status == 200
    assert resp.body["application"] is None


def test_recommendation_detail_application_none_without_action_service(env):
    _, _, _, orchestrator = env
    # Sans ActionService câblé, le détail reste lisible et n'affirme aucune intention.
    api_without_actions = HermesApi(orchestrator)
    resp = api_without_actions.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp.status == 200
    assert resp.body["application"] is None


# --- Candidature réellement effectuée : « j'ai candidaté » -------------------

def test_mark_applied_requires_noted_intent(env):
    api, applications, _, _ = env
    _approve(api)  # décision OK mais AUCUNE intention notée
    resp = api.dispatch("POST", f"/applications/{_RID}/applied", None)
    assert resp.status == 409
    assert "intention" in resp.body["error"]
    assert applications.count() == 0  # rien créé


def test_mark_applied_after_intent_sets_date_then_idempotent(env):
    api, applications, _, _ = env
    _approve(api)
    api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})

    first = api.dispatch("POST", f"/applications/{_RID}/applied", None)
    assert first.status == 200
    assert first.body["applied"] is True
    assert first.body["applied_at"] == "2026-09-05T00:00:00+00:00"
    assert applications.count() == 1  # pas de nouvelle action, la même est marquée

    # Re-déclarer ne recrée rien et ne réécrit pas la date (idempotent).
    second = api.dispatch("POST", f"/applications/{_RID}/applied", None)
    assert second.status == 200
    assert second.body["applied"] is True
    assert second.body["applied_at"] == "2026-09-05T00:00:00+00:00"
    assert applications.count() == 1


def test_recommendation_detail_reflects_applied(env):
    api, _, _, _ = env
    _approve(api)
    api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    api.dispatch("POST", f"/applications/{_RID}/applied", None)

    resp = api.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp.body["application"]["applied"] is True
    assert resp.body["application"]["applied_at"] == "2026-09-05T00:00:00+00:00"


def test_mark_applied_route_absent_without_action_service(env):
    _, _, _, orchestrator = env
    api_without_actions = HermesApi(orchestrator)
    resp = api_without_actions.dispatch("POST", f"/applications/{_RID}/applied", None)
    assert resp.status == 404


def test_application_store_migrates_legacy_table_without_applied_at():
    """Une base créée avant l'ajout de ``applied_at`` est migrée au branchement du store."""
    conn = connect(":memory:")
    # Reproduit l'ancien schéma (sans ``applied_at``) + une ligne « intention notée ».
    conn.execute(
        "CREATE TABLE application_actions ("
        "action_id TEXT PRIMARY KEY, recommendation_id TEXT NOT NULL UNIQUE, "
        "candidate_id TEXT NOT NULL, decision_status_at_confirmation TEXT NOT NULL, "
        "confirmed_at TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO application_actions VALUES "
        "('a1', 'r1', 'cand-1', 'approved', '2026-09-05T00:00:00+00:00', "
        "'2026-09-05T00:00:00+00:00', 'simulated')"
    )
    conn.commit()

    store = ApplicationActionStore(conn)  # doit ALTER TABLE sans perdre la ligne
    legacy = store.get_by_recommendation("r1")
    assert legacy is not None
    assert legacy.applied_at is None  # historique = intention sans candidature déclarée
    conn.close()


# --- Message : garde confirm + cible inconnue + pas de garde approved --------

@pytest.mark.parametrize("bad_body", [{}, {"confirm": False}, {"confirm": "true"}, {"confirm": 1}])
def test_confirm_message_requires_confirm_true(env, bad_body):
    api, _, messages, _ = env
    resp = api.dispatch("POST", f"/messages/{_RID}/confirm", bad_body)
    assert resp.status == 400
    assert messages.count() == 0


def test_confirm_message_unknown_target_is_404(env):
    api, _, messages, _ = env
    resp = api.dispatch("POST", "/messages/ghost/confirm", {"confirm": True})
    assert resp.status == 404
    assert "cible inconnue" in resp.body["error"]
    assert messages.count() == 0


def test_confirm_message_does_not_require_approved(env):
    api, _, messages, _ = env
    # Décision encore pending : contacter n'est pas gated sur approved → succès.
    first = api.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True})
    assert first.status == 200
    assert first.body == {"action_id": "msg_1", "status": "simulated", "already_confirmed": False}
    assert messages.count() == 1

    second = api.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True})
    assert second.body == {"action_id": "msg_1", "status": "simulated", "already_confirmed": True}
    assert messages.count() == 1  # idempotent par contact_id


# --- Méthode et montage ------------------------------------------------------

def test_wrong_method_returns_405(env):
    api, _, _, _ = env
    resp = api.dispatch("GET", f"/applications/{_RID}/confirm", None)
    assert resp.status == 405


def test_action_routes_absent_when_service_not_configured(env):
    _, _, _, orchestrator = env
    api_without_actions = HermesApi(orchestrator)  # pas d'ActionService
    resp = api_without_actions.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert resp.status == 404
    assert "route inconnue" in resp.body["error"]
