"""Tests de la note d'un modèle téléchargé par Opportune (OPP-251, OPP-252)."""

from app.model_download_recorder import make_download_recorder
from app.model_origin import MODELS_DIR_ENV, ModelOriginStore
from app.ollama_provision import OllamaUnreachable

_APP_DIR = "/donnees/opportune/ollama-models"


def test_recorder_notes_tagged_model_directory_and_fingerprint(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")
    record = make_download_recorder(
        store,
        host="127.0.0.1:11434",
        environ={MODELS_DIR_ENV: _APP_DIR},
        modified_at=lambda model, host=None: "2026-11-10T10:00:00Z",
    )

    record("ministral-3")

    assert store.fingerprint_of("ministral-3:latest", _APP_DIR) == "2026-11-10T10:00:00Z"


def test_recorder_notes_no_directory_when_user_ollama_is_in_use(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")
    environ_reusing_user_ollama = {}
    record = make_download_recorder(
        store,
        host="127.0.0.1:11434",
        environ=environ_reusing_user_ollama,
        modified_at=lambda model, host=None: "2026-11-10T10:00:00Z",
    )

    record("ministral-3:3b")

    assert store.was_downloaded_by_opportune("ministral-3:3b", None) is True


def test_recorder_notes_download_without_fingerprint_when_ollama_is_unreachable(tmp_path):
    def unreachable(model, host=None):
        raise OllamaUnreachable("refus")

    store = ModelOriginStore(tmp_path / "llm-model-origin.json")
    record = make_download_recorder(store, host="127.0.0.1:11434", environ={}, modified_at=unreachable)

    record("ministral-3:3b")

    assert store.was_downloaded_by_opportune("ministral-3:3b", None) is True
    assert store.fingerprint_of("ministral-3:3b", None) is None
