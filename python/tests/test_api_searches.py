"""Tests des routes CRUD « recherche » de l'API Hermes (OPP-184, tranche 1 back).

``/searches`` expose le périmètre de l'espace (le registre des candidats) : lister, créer une
recherche nommée, la renommer. On vérifie le contrat, les gardes (reviewer pour modifier, lecture
pour tous), l'anti-énumération (404 neutre sur un id inconnu) et surtout que **créer une recherche
l'inscrit aussitôt dans le périmètre** (``owned_candidate_ids`` de ``/me``) — c'est le même registre
qui alimente l'auth. Les routes ne sont montées que si le registre est câblé (sinon 404 neutre).
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User
from app.candidate_registry import CandidateRegistry
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

OWNER = User("moi", REVIEWER, frozenset())
VIEWER = User("moi", "viewer", frozenset())


@pytest.fixture
def env():
    conn = connect(":memory:")
    registry = CandidateRegistry(conn)
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )

    def api_as(user: User) -> HermesApi:
        # Le périmètre de l'auth dérive du MÊME registre que celui exposé par /searches.
        auth = LocalAuthProvider(user, owned_provider=registry.list_ids)
        return HermesApi(orchestrator, auth=auth, searches=registry)

    yield api_as
    conn.close()


def test_get_searches_lists_registry(env):
    api = env(OWNER)
    api.dispatch("POST", "/searches", {"label": "Data Analyst Paris"})
    api.dispatch("POST", "/searches", {"label": "Product Manager"})
    resp = api.dispatch("GET", "/searches")
    assert resp.status == 200
    labels = [item["label"] for item in resp.body["items"]]
    assert sorted(labels) == ["Data Analyst Paris", "Product Manager"]
    # Chaque item porte un id technique non vide.
    assert all(item["id"] for item in resp.body["items"])


def test_create_search_enters_perimeter(env):
    api = env(OWNER)
    created = api.dispatch("POST", "/searches", {"label": "Data Analyst"})
    assert created.status == 201
    new_id = created.body["id"]
    assert created.body["label"] == "Data Analyst"
    # La recherche entre AUSSITÔT dans le périmètre d'auth (même registre) : /me la voit.
    me = api.dispatch("GET", "/me")
    assert new_id in me.body["owned_candidate_ids"]
    assert me.body["owned_count"] == 1


def test_create_search_trims_label(env):
    api = env(OWNER)
    created = api.dispatch("POST", "/searches", {"label": "  Lead Dev  "})
    assert created.body["label"] == "Lead Dev"


@pytest.mark.parametrize("body", [{}, {"label": ""}, {"label": "   "}, {"label": 42}])
def test_create_search_rejects_bad_label(env, body):
    assert env(OWNER).dispatch("POST", "/searches", body).status == 400


def test_create_search_rejects_too_long_label(env):
    assert env(OWNER).dispatch("POST", "/searches", {"label": "x" * 200}).status == 400


def test_create_search_requires_reviewer(env):
    assert env(VIEWER).dispatch("POST", "/searches", {"label": "Essai"}).status == 403


def test_rename_search(env):
    api = env(OWNER)
    new_id = api.dispatch("POST", "/searches", {"label": "Ancien"}).body["id"]
    resp = api.dispatch("PUT", f"/searches/{new_id}", {"label": "Nouveau"})
    assert resp.status == 200
    assert resp.body == {"id": new_id, "label": "Nouveau"}
    labels = [item["label"] for item in api.dispatch("GET", "/searches").body["items"]]
    assert labels == ["Nouveau"]


def test_rename_unknown_search_is_404(env):
    assert env(OWNER).dispatch("PUT", "/searches/search-absent", {"label": "x"}).status == 404


def test_rename_requires_reviewer(env):
    api = env(OWNER)
    new_id = api.dispatch("POST", "/searches", {"label": "Ancien"}).body["id"]
    assert env(VIEWER).dispatch("PUT", f"/searches/{new_id}", {"label": "x"}).status == 403


def test_rename_rejects_bad_label(env):
    api = env(OWNER)
    new_id = api.dispatch("POST", "/searches", {"label": "Ancien"}).body["id"]
    assert api.dispatch("PUT", f"/searches/{new_id}", {"label": ""}).status == 400


def test_searches_wrong_method_is_405(env):
    assert env(OWNER).dispatch("DELETE", "/searches").status == 405


def test_searches_not_mounted_without_registry():
    # Sans registre câblé, les routes ne sont pas montées : 404 neutre (route inconnue).
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator, auth=LocalAuthProvider(OWNER))
    assert api.dispatch("GET", "/searches").status == 404
    assert api.dispatch("POST", "/searches", {"label": "x"}).status == 404
    conn.close()
