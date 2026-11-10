"""Tests de la route de désinstallation (/system/uninstall, OPP-252).

Le service est réel sur un dossier temporaire ; Ollama est simulé. On vérifie le contrat HTTP.
"""

import json

from api.app import HermesApi
from app.auth import LocalAuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.model_origin import ModelOriginStore
from app.offer_store import OfferStore
from app.ollama_provision import OllamaUnreachable
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from app.uninstall_service import INSTALL_KIND_ENV, REQUEST_FILENAME, UninstallService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

OWNER = User("moi", frozenset({"cand-1"}))


def _api(uninstall) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=LocalAuthProvider(OWNER), uninstall=uninstall)


def _service(tmp_path, *, environ, delete=lambda model, host=None: None) -> UninstallService:
    return UninstallService(
        data_dir=tmp_path,
        origin=ModelOriginStore(tmp_path / "llm-model-origin.json"),
        model="ministral-3:3b",
        host="127.0.0.1:11434",
        environ=environ,
        modified_at=lambda model, host=None: "2026-11-10T10:00:00Z",
        delete=delete,
    )


def test_get_returns_uninstall_info(tmp_path):
    api = _api(_service(tmp_path, environ={INSTALL_KIND_ENV: "appimage", "APPIMAGE": "/tmp/O.AppImage"}))

    response = api.dispatch("GET", "/system/uninstall")

    assert response.status == 200
    assert response.body["available"] is True
    assert response.body["install_kind"] == "appimage"
    assert response.body["appimage_path"] == "/tmp/O.AppImage"


def test_post_records_request_and_returns_202(tmp_path):
    api = _api(_service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}))

    response = api.dispatch("POST", "/system/uninstall", {"remove_model": True, "remove_data": False})

    assert response.status == 202
    assert json.loads((tmp_path / REQUEST_FILENAME).read_text(encoding="utf-8")) == {
        "remove_model": True,
        "remove_data": False,
    }


def test_post_rejects_missing_or_non_boolean_choices(tmp_path):
    api = _api(_service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}))

    missing_choice = api.dispatch("POST", "/system/uninstall", {"remove_model": True})
    non_boolean_choice = api.dispatch("POST", "/system/uninstall", {"remove_model": "oui", "remove_data": 1})

    assert missing_choice.status == 400
    assert non_boolean_choice.status == 400
    assert not (tmp_path / REQUEST_FILENAME).exists()


def test_post_is_409_outside_desktop_app(tmp_path):
    api = _api(_service(tmp_path, environ={}))

    response = api.dispatch("POST", "/system/uninstall", {"remove_model": False, "remove_data": False})

    assert response.status == 409
    assert not (tmp_path / REQUEST_FILENAME).exists()


def test_post_is_502_when_user_ollama_fails_to_delete_the_model(tmp_path):
    def fail_to_delete(model, host=None):
        raise OllamaUnreachable("refus")

    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(
        "ministral-3:3b", None, "2026-11-10T10:00:00Z"
    )
    api = _api(_service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}, delete=fail_to_delete))

    response = api.dispatch("POST", "/system/uninstall", {"remove_model": True, "remove_data": True})

    assert response.status == 502
    assert not (tmp_path / REQUEST_FILENAME).exists()


def test_other_methods_are_rejected(tmp_path):
    api = _api(_service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}))

    response = api.dispatch("DELETE", "/system/uninstall")

    assert response.status == 405


def test_route_is_404_when_service_is_not_wired():
    api = _api(None)

    response = api.dispatch("GET", "/system/uninstall")

    assert response.status == 404
