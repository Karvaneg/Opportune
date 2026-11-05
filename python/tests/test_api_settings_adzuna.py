"""Tests des endpoints de saisie des identifiants Adzuna (/settings/adzuna, OPP-222).

Le store est réel mais pointé sur un fichier temporaire (aucun secret réel, aucun réseau). On
vérifie le contrat HTTP : état « configuré » (jamais les clés), enregistrement, validation,
réservation au reviewer, et 404 quand le store n'est pas câblé.
"""

from api.app import HermesApi
from app.adzuna_credentials_store import AdzunaCredentialsStore
from app.auth import REVIEWER, LocalAuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

REVIEWER_USER = User("moi", REVIEWER, frozenset({"cand-1"}))
VIEWER_USER = User("moi", "viewer", frozenset({"cand-1"}))


def _api(store, *, user=REVIEWER_USER) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(
        orchestrator, auth=LocalAuthProvider(user), adzuna_credentials=store
    )


def test_get_reports_not_configured_on_empty_store(tmp_path):
    api = _api(AdzunaCredentialsStore(tmp_path / "adzuna.json"))

    response = api.dispatch("GET", "/settings/adzuna", None, None)

    assert response.status == 200
    assert response.body == {"configured": False}


def test_put_saves_credentials_and_reports_configured(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")
    api = _api(store)

    response = api.dispatch("PUT", "/settings/adzuna", {"app_id": "id", "app_key": "key"})

    assert response.status == 200
    assert response.body == {"configured": True}
    assert store.load().app_id == "id"


def test_get_reports_configured_after_save(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")
    api = _api(store)
    api.dispatch("PUT", "/settings/adzuna", {"app_id": "id", "app_key": "key"})

    response = api.dispatch("GET", "/settings/adzuna", None, None)

    assert response.body == {"configured": True}


def test_response_never_exposes_the_keys(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")
    api = _api(store)

    put = api.dispatch("PUT", "/settings/adzuna", {"app_id": "secret-id", "app_key": "secret-key"})
    get = api.dispatch("GET", "/settings/adzuna", None, None)

    assert "secret-id" not in str(put.body) and "secret-key" not in str(put.body)
    assert "app_id" not in get.body and "app_key" not in get.body


def test_put_rejects_missing_or_empty_fields(tmp_path):
    api = _api(AdzunaCredentialsStore(tmp_path / "adzuna.json"))

    assert api.dispatch("PUT", "/settings/adzuna", {"app_id": "id"}).status == 400
    assert api.dispatch("PUT", "/settings/adzuna", {"app_id": "id", "app_key": ""}).status == 400
    assert api.dispatch("PUT", "/settings/adzuna", {"app_id": 123, "app_key": "k"}).status == 400


def test_requires_reviewer_role(tmp_path):
    viewer = _api(AdzunaCredentialsStore(tmp_path / "adzuna.json"), user=VIEWER_USER)

    assert viewer.dispatch("GET", "/settings/adzuna", None, None).status == 403
    assert (
        viewer.dispatch("PUT", "/settings/adzuna", {"app_id": "id", "app_key": "key"}).status
        == 403
    )


def test_route_absent_without_store():
    api = _api(None)

    response = api.dispatch("GET", "/settings/adzuna", None, None)

    assert response.status == 404
