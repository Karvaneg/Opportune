"""Tests du service de désinstallation (OPP-252). Aucun réseau : Ollama est simulé."""

import json

import pytest

from app.model_origin import MODELS_DIR_ENV, ModelOriginStore
from app.ollama_provision import OllamaUnreachable
from app.uninstall_service import (
    APP_MODELS_DIRNAME,
    INSTALL_KIND_ENV,
    REQUEST_FILENAME,
    USER_OLLAMA_ENV,
    ModelRemovalFailed,
    UninstallNotAvailable,
    UninstallService,
)

_MODEL = "ministral-3:3b"
_USER_DIR = "/home/marie/.ollama/models"
# Empreinte (date de modification) de la copie téléchargée par Opportune, et celle d'une copie
# que la personne aurait retéléchargée plus tard.
_OPPORTUNE_COPY = "2026-11-10T10:00:00Z"
_USER_COPY = "2026-12-01T09:30:00Z"


def _service(tmp_path, *, environ, present=True, fingerprint=_OPPORTUNE_COPY, delete=None, deleted_models=None):
    """Service sur un dossier de données temporaire, avec un Ollama simulé : ``present`` dit si
    Ollama a le modèle, ``fingerprint`` la date de modification qu'il en donne."""

    def record_deletion(model, host=None):
        if deleted_models is not None:
            deleted_models.append(model)

    return UninstallService(
        data_dir=tmp_path,
        origin=ModelOriginStore(tmp_path / "llm-model-origin.json"),
        model=_MODEL,
        host="127.0.0.1:11434",
        environ=environ,
        modified_at=lambda model, host=None: fingerprint if present else None,
        delete=delete or record_deletion,
    )


def _put_model_in_app_dir(tmp_path, size_bytes=5):
    blobs = tmp_path / APP_MODELS_DIRNAME / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "sha256-abc").write_bytes(b"x" * size_bytes)


def test_uninstall_is_not_available_outside_desktop_app(tmp_path):
    environ_without_desktop_shell = {}

    info = _service(tmp_path, environ=environ_without_desktop_shell).info()

    assert info["available"] is False
    assert info["install_kind"] is None


def test_info_reports_install_kind_and_data_dir(tmp_path):
    environ = {INSTALL_KIND_ENV: "deb"}

    info = _service(tmp_path, environ=environ).info()

    assert info["available"] is True
    assert info["install_kind"] == "deb"
    assert info["data_dir"] == str(tmp_path)


def test_info_gives_appimage_path_only_for_appimage(tmp_path):
    appimage_environ = {INSTALL_KIND_ENV: "appimage", "APPIMAGE": "/home/marie/Opportune.AppImage"}
    deb_environ = {INSTALL_KIND_ENV: "deb", "APPIMAGE": "/home/marie/Opportune.AppImage"}

    assert _service(tmp_path, environ=appimage_environ).info()["appimage_path"] == "/home/marie/Opportune.AppImage"
    assert _service(tmp_path, environ=deb_environ).info()["appimage_path"] is None


def test_model_in_app_dir_is_removable_with_its_size(tmp_path):
    _put_model_in_app_dir(tmp_path, size_bytes=5)
    environ = {INSTALL_KIND_ENV: "deb", MODELS_DIR_ENV: str(tmp_path / APP_MODELS_DIRNAME)}

    model = _service(tmp_path, environ=environ).info()["model"]

    assert model == {"name": _MODEL, "present": True, "removable": True, "app_copy_bytes": 5}


def test_model_in_app_dir_is_removable_even_when_user_ollama_is_in_use(tmp_path):
    _put_model_in_app_dir(tmp_path)
    environ_reusing_user_ollama = {INSTALL_KIND_ENV: "deb"}

    model = _service(tmp_path, environ=environ_reusing_user_ollama, present=False).info()["model"]

    assert model["removable"] is True


def test_preexisting_model_is_present_but_not_removable(tmp_path):
    environ_serving_from_user_dir = {INSTALL_KIND_ENV: "deb", MODELS_DIR_ENV: _USER_DIR}

    model = _service(tmp_path, environ=environ_serving_from_user_dir, present=True).info()["model"]

    assert model["present"] is True
    assert model["removable"] is False


def test_model_downloaded_through_user_ollama_is_removable(tmp_path):
    environ_reusing_user_ollama = {INSTALL_KIND_ENV: "deb"}
    service = _service(tmp_path, environ=environ_reusing_user_ollama, present=True)
    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)

    model = service.info()["model"]

    assert model["removable"] is True
    assert model["app_copy_bytes"] == 0


def test_model_downloaded_through_user_ollama_then_removed_by_user_is_not_removable(tmp_path):
    environ_reusing_user_ollama = {INSTALL_KIND_ENV: "deb"}
    service = _service(tmp_path, environ=environ_reusing_user_ollama, present=False)
    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)

    model = service.info()["model"]

    assert model["removable"] is False
    assert model["present"] is False


def test_model_redownloaded_by_user_is_not_removable(tmp_path):
    environ_reusing_user_ollama = {INSTALL_KIND_ENV: "deb"}
    service = _service(tmp_path, environ=environ_reusing_user_ollama, fingerprint=_USER_COPY)
    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)

    model = service.info()["model"]

    assert model["present"] is True
    assert model["removable"] is False


def test_model_downloaded_without_known_fingerprint_is_not_removable(tmp_path):
    environ_reusing_user_ollama = {INSTALL_KIND_ENV: "deb"}
    service = _service(tmp_path, environ=environ_reusing_user_ollama)
    unknown_fingerprint = None
    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(_MODEL, None, unknown_fingerprint)

    model = service.info()["model"]

    assert model["removable"] is False


def test_info_asks_ollama_only_once(tmp_path):
    ollama_calls = []

    def count_calls(model, host=None):
        ollama_calls.append(model)
        return _OPPORTUNE_COPY

    service = UninstallService(
        data_dir=tmp_path,
        origin=ModelOriginStore(tmp_path / "llm-model-origin.json"),
        model=_MODEL,
        host="127.0.0.1:11434",
        environ={INSTALL_KIND_ENV: "deb"},
        modified_at=count_calls,
    )

    service.info()

    assert len(ollama_calls) == 1


def test_model_is_absent_when_ollama_is_unreachable_and_app_dir_is_empty(tmp_path):
    def unreachable(model, host=None):
        raise OllamaUnreachable("refus")

    service = UninstallService(
        data_dir=tmp_path,
        origin=ModelOriginStore(tmp_path / "llm-model-origin.json"),
        model=_MODEL,
        host="127.0.0.1:11434",
        environ={INSTALL_KIND_ENV: "deb"},
        modified_at=unreachable,
    )

    model = service.info()["model"]

    assert model["present"] is False
    assert model["removable"] is False


def test_info_reports_user_own_ollama(tmp_path):
    environ_with_user_ollama = {INSTALL_KIND_ENV: "deb", USER_OLLAMA_ENV: "1"}
    environ_without_user_ollama = {INSTALL_KIND_ENV: "deb"}

    assert _service(tmp_path, environ=environ_with_user_ollama).info()["user_has_own_ollama"] is True
    assert _service(tmp_path, environ=environ_without_user_ollama).info()["user_has_own_ollama"] is False


def test_request_writes_the_choices_for_the_desktop_shell(tmp_path):
    service = _service(tmp_path, environ={INSTALL_KIND_ENV: "deb"})

    service.request(remove_model=True, remove_data=False)

    written_request = json.loads((tmp_path / REQUEST_FILENAME).read_text(encoding="utf-8"))
    assert written_request == {"remove_model": True, "remove_data": False}


def test_request_leaves_no_temporary_file(tmp_path):
    service = _service(tmp_path, environ={INSTALL_KIND_ENV: "deb"})

    service.request(remove_model=False, remove_data=True)

    assert sorted(path.name for path in tmp_path.iterdir()) == [REQUEST_FILENAME]


def test_request_is_refused_outside_desktop_app(tmp_path):
    service = _service(tmp_path, environ={})

    with pytest.raises(UninstallNotAvailable):
        service.request(remove_model=True, remove_data=True)

    assert not (tmp_path / REQUEST_FILENAME).exists()


def test_request_deletes_model_downloaded_through_user_ollama(tmp_path):
    deleted_models = []
    origin = ModelOriginStore(tmp_path / "llm-model-origin.json")
    origin.mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)
    service = _service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}, deleted_models=deleted_models)

    service.request(remove_model=True, remove_data=False)

    assert deleted_models == [_MODEL]
    assert origin.was_downloaded_by_opportune(_MODEL, None) is False


def test_request_never_deletes_a_model_redownloaded_by_user(tmp_path):
    deleted_models = []
    origin = ModelOriginStore(tmp_path / "llm-model-origin.json")
    origin.mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)
    service = _service(
        tmp_path, environ={INSTALL_KIND_ENV: "deb"}, fingerprint=_USER_COPY, deleted_models=deleted_models
    )

    service.request(remove_model=True, remove_data=False)

    assert deleted_models == []


def test_request_deletes_nothing_when_the_request_cannot_be_written(tmp_path):
    deleted_models = []
    data_dir_that_is_a_file = tmp_path / "pas-un-dossier"
    data_dir_that_is_a_file.write_text("x", encoding="utf-8")
    origin = ModelOriginStore(tmp_path / "llm-model-origin.json")
    origin.mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)
    service = UninstallService(
        data_dir=data_dir_that_is_a_file,
        origin=origin,
        model=_MODEL,
        host="127.0.0.1:11434",
        environ={INSTALL_KIND_ENV: "deb"},
        modified_at=lambda model, host=None: _OPPORTUNE_COPY,
        delete=lambda model, host=None: deleted_models.append(model),
    )

    with pytest.raises(OSError):
        service.request(remove_model=True, remove_data=True)

    assert deleted_models == []
    assert origin.was_downloaded_by_opportune(_MODEL, None) is True


def test_request_keeps_model_in_user_ollama_when_removal_is_not_asked(tmp_path):
    deleted_models = []
    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)
    service = _service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}, deleted_models=deleted_models)

    service.request(remove_model=False, remove_data=False)

    assert deleted_models == []


def test_request_never_deletes_a_preexisting_model(tmp_path):
    deleted_models = []
    environ_serving_from_user_dir = {INSTALL_KIND_ENV: "deb", MODELS_DIR_ENV: _USER_DIR}
    service = _service(tmp_path, environ=environ_serving_from_user_dir, deleted_models=deleted_models)

    service.request(remove_model=True, remove_data=False)

    assert deleted_models == []


def test_request_does_not_ask_ollama_to_delete_the_app_dir_copy(tmp_path):
    deleted_models = []
    _put_model_in_app_dir(tmp_path)
    environ = {INSTALL_KIND_ENV: "deb", MODELS_DIR_ENV: str(tmp_path / APP_MODELS_DIRNAME)}
    ModelOriginStore(tmp_path / "llm-model-origin.json").mark_downloaded(_MODEL, environ[MODELS_DIR_ENV])
    service = _service(tmp_path, environ=environ, deleted_models=deleted_models)

    service.request(remove_model=True, remove_data=False)

    assert deleted_models == []


def test_request_writes_nothing_when_user_ollama_fails_to_delete(tmp_path):
    def fail_to_delete(model, host=None):
        raise OllamaUnreachable("refus")

    origin = ModelOriginStore(tmp_path / "llm-model-origin.json")
    origin.mark_downloaded(_MODEL, None, _OPPORTUNE_COPY)
    service = _service(tmp_path, environ={INSTALL_KIND_ENV: "deb"}, delete=fail_to_delete)

    with pytest.raises(ModelRemovalFailed):
        service.request(remove_model=True, remove_data=True)

    assert sorted(path.name for path in tmp_path.iterdir()) == ["llm-model-origin.json"]
    assert origin.was_downloaded_by_opportune(_MODEL, None) is True
