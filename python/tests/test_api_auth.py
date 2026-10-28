"""Tests d'identité et d'autorisation de l'API Hermes (OPP-097, local-first OPP-181).

Matrice de sécurité sur ``HermesApi.dispatch`` (vrais dépôts SQLite en mémoire). Depuis
OPP-181 il n'y a **plus de jeton** : l'identité est locale (``LocalAuthProvider``) et toujours
résolue. On teste donc ce qui subsiste — et qu'OPP-183 (périmètre par recherche) réutilisera :
- **404** sur une ressource hors périmètre (on ne révèle pas son existence) ;
- **403** quand la ressource est possédée mais que le rôle ``reviewer`` manque ;
- succès pour l'utilisateur autorisé ; ordre des gardes des actions sensibles.

Pour simuler différents périmètres on compose plusieurs ``HermesApi`` sur la **même** base,
chacune portant une identité distincte (plus de bascule par en-tête). Plus la non-régression
du mode ouvert (``auth=None``) et des tests d'intégration vérifiant que la composition de
production (``server.assemble_api`` + ``create_server``) porte bien une identité et route les
verbes DELETE/PUT (sinon 501 avant le dispatcher).
"""

import http.client
import itertools
import threading
from types import SimpleNamespace

import pytest

from api.app import HermesApi
from api.server import assemble_api, create_server
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.auth import REVIEWER, LocalAuthProvider, User
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

# Trois identités locales sur la même base : propriétaire reviewer, propriétaire sans le rôle,
# et un tiers reviewer dont le périmètre (cand-2) ne couvre pas cand-1.
OWNER = User("moi", REVIEWER, frozenset({"cand-1"}))
VIEWER = User("moi", "viewer", frozenset({"cand-1"}))
FOREIGN = User("autre", REVIEWER, frozenset({"cand-2"}))


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

    def api_as(user: User) -> HermesApi:
        return HermesApi(orchestrator, actions, LocalAuthProvider(user))

    bench = SimpleNamespace(
        owner=api_as(OWNER), viewer=api_as(VIEWER), foreign=api_as(FOREIGN),
        orchestrator=orchestrator,
    )
    # Seed run-1 + décisions pending (le propriétaire lance la recommandation).
    bench.owner.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    yield bench
    conn.close()


# --- Propriété (404 pour ne pas révéler l'existence) -------------------------

def test_owner_can_read_run(env):
    assert env.owner.dispatch("GET", "/runs/run-1").status == 200


def test_delete_run_guards_existence_then_owner_then_reviewer(env):
    # OPP-144 : ordre des gardes identique aux actions sensibles.
    # autre est reviewer mais ne possède pas cand-1 → 404 neutre (propriété avant rôle).
    assert env.foreign.dispatch("DELETE", "/runs/run-1").status == 404
    # moi possède cand-1 mais n'est pas reviewer → 403.
    assert env.viewer.dispatch("DELETE", "/runs/run-1").status == 403
    # moi possède cand-1 et est reviewer → suppression effective.
    ok = env.owner.dispatch("DELETE", "/runs/run-1")
    assert ok.status == 200 and ok.body == {"deleted": "run-1"}
    # Puis le run a disparu.
    assert env.owner.dispatch("GET", "/runs/run-1").status == 404


@pytest.mark.parametrize("path", [
    "/runs/run-1",
    "/runs/run-1/recommendations",
    f"/recommendations/{_RID}",
])
def test_foreign_resource_is_404_not_403(env, path):
    # autre est reviewer, mais cand-1 n'est pas dans son périmètre → 404 (pas 403).
    assert env.foreign.dispatch("GET", path).status == 404


@pytest.mark.parametrize("existing,missing", [
    ("/runs/run-1", "/runs/ghost"),
    ("/runs/run-1/recommendations", "/runs/ghost/recommendations"),
    (f"/recommendations/{_RID}", f"/recommendations/{decision_id('cand-1', 'ghost')}"),
])
def test_foreign_and_missing_are_indistinguishable(env, existing, missing):
    """Anti-énumération : une ressource existante hors périmètre et une ressource
    inexistante renvoient un 404 au **corps identique** — sinon l'existence fuite."""
    foreign = env.foreign.dispatch("GET", existing)   # existe, hors périmètre d'autre
    absent = env.foreign.dispatch("GET", missing)      # n'existe pas
    assert foreign.status == absent.status == 404
    assert foreign.body == absent.body


def test_sensitive_action_foreign_and_missing_indistinguishable(env):
    """Même garantie sur les actions sensibles (cible existante d'autrui vs inexistante)."""
    ghost = decision_id("cand-1", "ghost")
    foreign = env.foreign.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    absent = env.foreign.dispatch("POST", f"/applications/{ghost}/confirm", {"confirm": True})
    assert foreign.status == absent.status == 404
    assert foreign.body == absent.body


def test_post_recommendations_foreign_candidate_is_404(env):
    assert env.foreign.dispatch(
        "POST", "/candidates/cand-1/recommendations", {"limit": 5}
    ).status == 404


def test_post_recommendations_owner_without_reviewer_ok(env):
    # moi possède cand-1 mais n'est pas reviewer : lancer une reco ne l'exige pas.
    assert env.viewer.dispatch(
        "POST", "/candidates/cand-1/recommendations", {"limit": 5}
    ).status == 200


def test_rescore_foreign_candidate_is_404(env):
    # OPP-150 : re-score hors périmètre → 404 neutre (propriété avant tout).
    assert env.foreign.dispatch(
        "POST", "/candidates/cand-1/offers/off-app/rescore", {}
    ).status == 404


def test_rescore_owner_without_reviewer_ok(env):
    # moi possède cand-1 sans le rôle reviewer : re-scorer une offre ne l'exige pas.
    resp = env.viewer.dispatch("POST", "/candidates/cand-1/offers/off-app/rescore", {})
    assert resp.status == 200
    assert resp.body["offer_id"] == "off-app"


# --- Rôle reviewer (403) : validation humaine et actions sensibles -----------

def test_decision_requires_reviewer_role(env):
    # moi possède la ressource mais n'a pas le rôle → 403.
    assert env.viewer.dispatch(
        "POST", f"/recommendations/{_RID}/decision", {"decision": "approve"}
    ).status == 403
    # moi (owner) possède ET est reviewer → succès.
    ok = env.owner.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"})
    assert ok.status == 200
    assert ok.body["status"] == "approved"


def test_decision_ownership_checked_before_role(env):
    # autre est reviewer mais hors périmètre → 404 (existence/propriété), pas 403.
    assert env.foreign.dispatch(
        "POST", f"/recommendations/{_RID}/decision", {"decision": "approve"}
    ).status == 404


def test_decision_unknown_recommendation_is_404(env):
    ghost = decision_id("cand-1", "ghost")
    assert env.owner.dispatch(
        "POST", f"/recommendations/{ghost}/decision", {"decision": "approve"}
    ).status == 404


# --- Actions sensibles : chaîne existence → propriété → rôle → confirm -------

def test_confirm_application_authz_chain(env):
    # Hors périmètre → 404 (avant même la garde confirm).
    assert env.foreign.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}).status == 404
    # Possède mais pas reviewer → 403.
    assert env.viewer.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}).status == 403
    # Reviewer + propriétaire mais confirm manquant → 400 (garde après la chaîne).
    assert env.owner.dispatch("POST", f"/applications/{_RID}/confirm", {}).status == 400
    # Reviewer + propriétaire + confirm mais décision pending → 409.
    assert env.owner.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True}).status == 409
    # Après validation humaine, la confirmation aboutit.
    env.owner.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "approve"})
    ok = env.owner.dispatch("POST", f"/applications/{_RID}/confirm", {"confirm": True})
    assert ok.status == 200
    assert ok.body["already_confirmed"] is False


def test_confirm_message_authz_chain(env):
    assert env.foreign.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True}).status == 404
    assert env.viewer.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True}).status == 403
    # Reviewer + propriétaire : contacter ne requiert pas approved → succès direct.
    assert env.owner.dispatch("POST", f"/messages/{_RID}/confirm", {"confirm": True}).status == 200


def test_wrong_method_still_405(env):
    assert env.owner.dispatch("GET", f"/recommendations/{_RID}/decision").status == 405


# --- Non-régression : mode ouvert (auth=None) --------------------------------

def test_open_mode_serves_without_identity(env):
    open_api = HermesApi(env.orchestrator)  # pas de fournisseur d'identité
    resp = open_api.dispatch("GET", "/runs/run-1")
    assert resp.status == 200  # aucune restriction


# --- Intégration : la composition de production porte une identité -----------

def test_assemble_api_carries_identity():
    conn = connect(":memory:")
    _profile(conn)
    OfferStore(conn).save(_offer())
    auth = LocalAuthProvider(OWNER)
    api = assemble_api(conn, auth)
    assert api.auth is auth
    # L'identité locale possède cand-1 → l'action aboutit sans aucun jeton.
    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 5})
    assert resp.status == 200
    conn.close()


def test_assemble_api_refuses_open_mode():
    conn = connect(":memory:")
    with pytest.raises(ValueError):
        assemble_api(conn, None)
    conn.close()


def test_server_serves_me_over_http():
    """Bout-en-bout : le serveur HTTP réel route ``GET /api/me`` et renvoie l'identité locale.

    Depuis OPP-191 l'API sert aussi le front : les appels de données sont préfixés ``/api``
    (les requêtes nues relèvent du front / des routes client). ``/me`` ne touche pas SQLite →
    sûr depuis le thread serveur. Valide que l'adaptateur retire le préfixe, transmet la
    requête, et que l'identité est bien servie **sans jeton**.
    """
    conn = connect(":memory:")
    _profile(conn)
    OfferStore(conn).save(_offer())
    server = create_server(assemble_api(conn, LocalAuthProvider(OWNER)), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = http.client.HTTPConnection(host, port, timeout=5)
        client.request("GET", "/api/me")
        resp = client.getresponse()
        assert resp.status == 200
        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    conn.close()


def test_server_serves_front_and_routes_api(tmp_path):
    """OPP-191 : avec un ``static_dir``, le serveur sert le front à la racine et route ``/api``.

    - ``GET /`` → index.html (200, text/html) ;
    - ``GET /runs/42`` (route client, sans extension) → fallback SPA sur index.html ;
    - ``GET /api/me`` → dispatcher (200, JSON) : le préfixe cohabite avec le statique.
    """
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Opportune</title>")

    conn = connect(":memory:")
    _profile(conn)
    server = create_server(
        assemble_api(conn, LocalAuthProvider(OWNER)), port=0, static_dir=dist
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = http.client.HTTPConnection(host, port, timeout=5)

        client.request("GET", "/")
        root = client.getresponse()
        root_body = root.read()
        assert root.status == 200
        assert root.getheader("Content-Type").startswith("text/html")
        assert b"Opportune" in root_body

        client.request("GET", "/runs/42")
        spa = client.getresponse()
        assert spa.status == 200
        assert b"Opportune" in spa.read()

        client.request("GET", "/api/me")
        me = client.getresponse()
        assert me.status == 200
        assert me.getheader("Content-Type").startswith("application/json")
        me.read()

        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    conn.close()


@pytest.mark.parametrize("method", ["DELETE", "PUT"])
def test_server_supports_delete_and_put_methods_over_http(method):
    """Régression OPP-144/147 : ``http.server`` doit exposer ``do_DELETE`` et ``do_PUT``
    (sinon 501 *avant* le dispatcher, qui route DELETE /runs/{id} et PUT …/letter). On vise un
    chemin **non routé** : une méthode câblée répond 404 (route inconnue, sans accès base) — un
    501 trahirait une méthode non montée côté transport.
    """
    conn = connect(":memory:")
    _profile(conn)
    OfferStore(conn).save(_offer())
    server = create_server(assemble_api(conn, LocalAuthProvider(OWNER)), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = http.client.HTTPConnection(host, port, timeout=5)
        client.request(method, "/__non_route__", body="{}", headers={"Content-Type": "application/json"})
        assert client.getresponse().status != 501  # câblé (404 attendu, ≠ « méthode non supportée »)
        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    conn.close()


# --- GET /me : identité locale (OPP-103, local-first OPP-181) ----------------

def test_me_returns_local_identity(env):
    resp = env.owner.dispatch("GET", "/me")
    assert resp.status == 200
    assert resp.body == {
        "id": "moi",
        "role": REVIEWER,
        "owned_count": 1,
        # OPP-143 : les candidats du propriétaire, pour lancer un run depuis le front.
        "owned_candidate_ids": ["cand-1"],
    }


def test_me_reflects_role_and_scope(env):
    # viewer : rôle non-reviewer ; foreign : reviewer, périmètre cand-2.
    assert env.viewer.dispatch("GET", "/me").body["role"] == "viewer"
    assert env.foreign.dispatch("GET", "/me").body["id"] == "autre"
    assert env.foreign.dispatch("GET", "/me").body["owned_candidate_ids"] == ["cand-2"]


def test_me_rejects_non_get(env):
    assert env.owner.dispatch("POST", "/me", {}).status == 405


def test_me_open_mode_has_no_identity():
    # Sans fournisseur (mode ouvert/test) : route accessible, identité nulle.
    conn = connect(":memory:")
    _profile(conn)
    OfferStore(conn).save(_offer())
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    resp = HermesApi(orchestrator).dispatch("GET", "/me")
    assert resp.status == 200
    assert resp.body == {"id": None, "role": None, "owned_count": 0, "owned_candidate_ids": []}
    conn.close()
