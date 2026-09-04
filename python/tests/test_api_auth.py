"""Tests d'authentification et d'autorisation de l'API Hermes (OPP-097).

Matrice de sécurité sur ``HermesApi.dispatch`` (vrais dépôts SQLite en mémoire) :
- **401** sans jeton / jeton invalide ;
- **404** sur une ressource hors périmètre (on ne révèle pas son existence) ;
- **403** quand la ressource est possédée mais que le rôle ``reviewer`` manque ;
- succès pour l'utilisateur autorisé ; ordre des gardes des actions sensibles.

Plus la **non-régression** du mode ouvert (``auth=None``) et deux tests d'intégration
vérifiant que la composition de production (``server.assemble_api`` + ``create_server``)
**active** bien l'authentification.
"""

import http.client
import itertools
import threading

import pytest

from api.app import HermesApi
from api.server import assemble_api, create_server
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.auth import REVIEWER, AuthProvider, User
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


def _profile(conn):
    ProfileStore(conn).save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))


_RID = decision_id("cand-1", "off-app")


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def env():
    conn = connect(":memory:")
    _profile(conn)
    offers = OfferStore(conn)
    offers.save(_offer())
    decisions = DecisionService(DecisionStore(conn), now=lambda: "2026-09-04T00:00:00+00:00")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), offers),
        decisions,
        runs=RunStore(conn),
        run_id=lambda: "run-1",
        now=lambda: "2026-09-04T12:00:00+00:00",
    )
    ids = (str(n) for n in itertools.count(1))
    actions = ActionService(
        decisions, ApplicationActionStore(conn), OutboundMessageActionStore(conn),
        new_id=lambda: next(ids), now=lambda: "2026-09-05T00:00:00+00:00",
    )
    # rev possède cand-1 et est reviewer ; view possède cand-1 sans le rôle ;
    # str est reviewer mais possède un autre périmètre (cand-2).
    auth = AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-view": User("view", "viewer", frozenset({"cand-1"})),
        "tok-str": User("str", REVIEWER, frozenset({"cand-2"})),
    })
    api = HermesApi(orchestrator, actions, auth)
    # Seed run-1 + décision pending (le propriétaire lance la recommandation).
    api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10}, _hdr("tok-rev"))
    yield api, orchestrator
    conn.close()


# --- Authentification (401) --------------------------------------------------

def test_missing_token_returns_401(env):
    api, _ = env
    resp = api.dispatch("GET", "/runs/run-1", None, None)
    assert resp.status == 401


@pytest.mark.parametrize("header", [
    {"Authorization": "Bearer wrong"},      # jeton inconnu (invalide/expiré)
    {"Authorization": "Bearer "},           # jeton vide
    {"Authorization": "tok-rev"},           # pas de schéma
    {"Authorization": "Basic tok-rev"},     # mauvais schéma
    {"X-Other": "tok-rev"},                 # pas d'en-tête Authorization
])
def test_invalid_token_returns_401(env, header):
    api, _ = env
    resp = api.dispatch("GET", "/runs/run-1", None, header)
    assert resp.status == 401


# --- Propriété (404 pour ne pas révéler l'existence) -------------------------

def test_owner_can_read_run(env):
    api, _ = env
    resp = api.dispatch("GET", "/runs/run-1", None, _hdr("tok-rev"))
    assert resp.status == 200


@pytest.mark.parametrize("path", [
    "/runs/run-1",
    "/runs/run-1/recommendations",
    f"/recommendations/{_RID}",
])
def test_foreign_resource_is_404_not_403(env, path):
    api, _ = env
    # str est authentifié et reviewer, mais cand-1 n'est pas dans son périmètre.
    resp = api.dispatch("GET", path, None, _hdr("tok-str"))
    assert resp.status == 404


def test_post_recommendations_foreign_candidate_is_404(env):
    api, _ = env
    resp = api.dispatch(
        "POST", "/candidates/cand-1/recommendations", {"limit": 5}, _hdr("tok-str")
    )
    assert resp.status == 404


def test_post_recommendations_owner_without_reviewer_ok(env):
    api, _ = env
    # view possède cand-1 mais n'est pas reviewer : lancer une reco ne l'exige pas.
    resp = api.dispatch(
        "POST", "/candidates/cand-1/recommendations", {"limit": 5}, _hdr("tok-view")
    )
    assert resp.status == 200


# --- Rôle reviewer (403) : validation humaine et actions sensibles -----------

def test_decision_requires_reviewer_role(env):
    api, _ = env
    # view possède la ressource mais n'a pas le rôle → 403.
    resp = api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"}, _hdr("tok-view"))
    assert resp.status == 403

    # rev possède ET est reviewer → succès.
    ok = api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"}, _hdr("tok-rev"))
    assert ok.status == 200
    assert ok.body["status"] == "approved"


def test_decision_ownership_checked_before_role(env):
    api, _ = env
    # str est reviewer mais hors périmètre → 404 (existence/propriété), pas 403.
    resp = api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"}, _hdr("tok-str"))
    assert resp.status == 404


def test_decision_unknown_recommendation_is_404(env):
    api, _ = env
    ghost = decision_id("cand-1", "ghost")
    resp = api.dispatch("POST", f"/recommendations/{ghost}/decision", {"decision": "approve"}, _hdr("tok-rev"))
    assert resp.status == 404


# --- Actions sensibles : chaîne existence → propriété → rôle → confirm -------

def test_confirm_application_authz_chain(env):
    api, _ = env
    # Hors périmètre → 404 (avant même la garde confirm).
    assert api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}, _hdr("tok-str")).status == 404
    # Possède mais pas reviewer → 403.
    assert api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}, _hdr("tok-view")).status == 403
    # Reviewer + propriétaire mais confirm manquant → 400 (garde après la chaîne).
    assert api.dispatch("POST", f"/applications/{_RID}/confirm", {}, _hdr("tok-rev")).status == 400
    # Reviewer + propriétaire + confirm mais décision pending → 409.
    assert api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}, _hdr("tok-rev")).status == 409
    # Après validation humaine, la confirmation aboutit.
    api.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"}, _hdr("tok-rev"))
    ok = api.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}, _hdr("tok-rev"))
    assert ok.status == 200
    assert ok.body["already_confirmed"] is False


def test_confirm_message_authz_chain(env):
    api, _ = env
    assert api.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True}, _hdr("tok-str")).status == 404
    assert api.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True}, _hdr("tok-view")).status == 403
    # Reviewer + propriétaire : contacter ne requiert pas approved → succès direct.
    ok = api.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True}, _hdr("tok-rev"))
    assert ok.status == 200


def test_wrong_method_still_405(env):
    api, _ = env
    resp = api.dispatch("GET", f"/recommendations/{_RID}/decision", None, _hdr("tok-rev"))
    assert resp.status == 405


# --- Non-régression : mode ouvert (auth=None) --------------------------------

def test_open_mode_needs_no_token(env):
    _, orchestrator = env
    open_api = HermesApi(orchestrator)  # pas d'AuthProvider
    resp = open_api.dispatch("GET", "/runs/run-1", None, None)
    assert resp.status == 200  # aucune authentification exigée


# --- Intégration : la composition de production active l'authentification -----

def test_assemble_api_enforces_auth_at_dispatch():
    conn = connect(":memory:")
    _profile(conn)
    OfferStore(conn).save(_offer())
    auth = AuthProvider({"tok": User("u", REVIEWER, frozenset({"cand-1"}))})
    api = assemble_api(conn, auth)
    assert api.auth is auth

    without = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 5}, None)
    assert without.status == 401
    with_token = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 5}, _hdr("tok"))
    assert with_token.status == 200
    conn.close()


def test_assemble_api_refuses_open_mode():
    conn = connect(":memory:")
    with pytest.raises(ValueError):
        assemble_api(conn, None)
    conn.close()


def test_server_rejects_unauthenticated_request_over_http():
    """Bout-en-bout : le serveur HTTP réel refuse (401) une requête sans jeton.

    Valide que l'adaptateur transmet bien les en-têtes et que l'auth s'applique avant tout
    accès base (le chemin 401 ne touche pas SQLite, donc sûr depuis le thread serveur ;
    check_same_thread interdit le chemin 200 cross-thread — couvert au niveau dispatch).
    """
    conn = connect(":memory:")
    _profile(conn)
    OfferStore(conn).save(_offer())
    auth = AuthProvider({"tok": User("u", REVIEWER, frozenset({"cand-1"}))})
    server = create_server(assemble_api(conn, auth), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = http.client.HTTPConnection(host, port, timeout=5)
        client.request(
            "POST", "/candidates/cand-1/recommendations",
            body="{}", headers={"Content-Type": "application/json"},
        )
        assert client.getresponse().status == 401
        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    conn.close()
