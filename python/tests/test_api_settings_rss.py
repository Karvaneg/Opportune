"""Tests des endpoints de saisie des URLs de flux RSS (/settings/rss, OPP-195).

Le store est réel mais pointé sur un fichier temporaire (aucun réseau). On vérifie le contrat
HTTP : lecture des URLs (non secrètes, relues telles quelles), enregistrement avec nettoyage,
validation, et 404 quand le store n'est pas câblé.
"""

from api.app import HermesApi
from app.auth import LocalAuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from app.rss_feeds_store import RssFeedsStore
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

LOCAL_USER = User("moi", frozenset({"cand-1"}))


def _api(store, *, user=LOCAL_USER) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=LocalAuthProvider(user), rss_feeds=store)


def test_get_reports_empty_list_on_empty_store(tmp_path):
    api = _api(RssFeedsStore(tmp_path / "rss.json"))

    response = api.dispatch("GET", "/settings/rss", None, None)

    assert response.status == 200
    assert response.body == {"feeds": []}


def test_put_saves_feeds_and_returns_cleaned_list(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")
    api = _api(store)

    response = api.dispatch(
        "PUT", "/settings/rss", {"feeds": ["  https://a.example/f  ", "ftp://skip", ""]}
    )

    assert response.status == 200
    assert response.body == {"feeds": ["https://a.example/f"]}
    assert store.load() == ["https://a.example/f"]


def test_get_returns_saved_feeds(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")
    api = _api(store)
    api.dispatch("PUT", "/settings/rss", {"feeds": ["https://a.example/f"]})

    response = api.dispatch("GET", "/settings/rss", None, None)

    assert response.body == {"feeds": ["https://a.example/f"]}


def test_put_rejects_non_list_or_no_usable_url(tmp_path):
    api = _api(RssFeedsStore(tmp_path / "rss.json"))

    assert api.dispatch("PUT", "/settings/rss", {"feeds": "https://a.example/f"}).status == 400
    assert api.dispatch("PUT", "/settings/rss", {"feeds": ["ftp://nope", ""]}).status == 400


def test_put_empty_list_removes_all_feeds(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")
    api = _api(store)
    api.dispatch("PUT", "/settings/rss", {"feeds": ["https://a.example/f"]})

    response = api.dispatch("PUT", "/settings/rss", {"feeds": []})

    assert response.status == 200
    assert response.body == {"feeds": []}
    assert store.load() == []


def test_put_reports_file_system_error_with_message(tmp_path):
    class LockedStore(RssFeedsStore):
        def clear(self):
            raise PermissionError("fichier verrouillé")

    api = _api(LockedStore(tmp_path / "rss.json"))

    response = api.dispatch("PUT", "/settings/rss", {"feeds": []})

    assert response.status == 500
    assert "fichier verrouillé" in response.body["error"]


def test_route_absent_without_store():
    api = _api(None)

    response = api.dispatch("GET", "/settings/rss", None, None)

    assert response.status == 404
