"""Tests de la trace d'origine du modèle LLM (OPP-251)."""

from app.model_origin import MODELS_DIR_ENV, ModelOriginStore, models_dir_from_env

_APP_DIR = "/donnees/opportune/ollama-models"
_USER_DIR = "/home/marie/.ollama/models"


def test_model_is_not_downloaded_by_opportune_when_file_is_missing(tmp_path):
    store_without_file = ModelOriginStore(tmp_path / "llm-model-origin.json")

    assert store_without_file.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is False


def test_marked_model_is_downloaded_by_opportune(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")

    store.mark_downloaded("ministral-3:3b", _APP_DIR)

    assert store.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is True


def test_same_model_in_another_directory_is_not_downloaded_by_opportune(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")

    store.mark_downloaded("ministral-3:3b", _APP_DIR)

    assert store.was_downloaded_by_opportune("ministral-3:3b", _USER_DIR) is False


def test_other_model_stays_not_downloaded_by_opportune(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")

    store.mark_downloaded("ministral-3:3b", _APP_DIR)

    assert store.was_downloaded_by_opportune("llama3:latest", _APP_DIR) is False


def test_download_through_user_ollama_is_recorded_without_directory(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")
    unknown_directory = None

    store.mark_downloaded("ministral-3:3b", unknown_directory)

    assert store.was_downloaded_by_opportune("ministral-3:3b", unknown_directory) is True
    assert store.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is False


def test_mark_is_kept_across_store_instances(tmp_path):
    origin_file = tmp_path / "llm-model-origin.json"
    ModelOriginStore(origin_file).mark_downloaded("ministral-3:3b", _APP_DIR)

    reopened_store = ModelOriginStore(origin_file)

    assert reopened_store.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is True


def test_marking_twice_keeps_a_single_entry(tmp_path):
    origin_file = tmp_path / "llm-model-origin.json"
    store = ModelOriginStore(origin_file)

    store.mark_downloaded("ministral-3:3b", _APP_DIR)
    store.mark_downloaded("ministral-3:3b", _APP_DIR)

    assert origin_file.read_text(encoding="utf-8").count("ministral-3:3b") == 1


def test_mark_creates_missing_data_directory(tmp_path):
    origin_file_in_missing_directory = tmp_path / "pas-encore-cree" / "llm-model-origin.json"

    ModelOriginStore(origin_file_in_missing_directory).mark_downloaded("ministral-3:3b", _APP_DIR)

    assert origin_file_in_missing_directory.is_file()


def test_unreadable_file_counts_as_not_downloaded(tmp_path):
    corrupted_file = tmp_path / "llm-model-origin.json"
    corrupted_file.write_text("pas du json", encoding="utf-8")

    store = ModelOriginStore(corrupted_file)

    assert store.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is False


def test_malformed_entries_are_ignored(tmp_path):
    file_with_malformed_entries = tmp_path / "llm-model-origin.json"
    file_with_malformed_entries.write_text(
        '{"downloaded_by_opportune": ["ministral-3:3b", {"models_dir": 3}, {"model": "llama3:latest", "models_dir": null}]}',
        encoding="utf-8",
    )

    store = ModelOriginStore(file_with_malformed_entries)

    assert store.was_downloaded_by_opportune("ministral-3:3b", None) is False
    assert store.was_downloaded_by_opportune("llama3:latest", None) is True


def test_mark_replaces_unreadable_file(tmp_path):
    corrupted_file = tmp_path / "llm-model-origin.json"
    corrupted_file.write_text("[1, 2]", encoding="utf-8")
    store = ModelOriginStore(corrupted_file)

    store.mark_downloaded("ministral-3:3b", _APP_DIR)

    assert store.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is True


def test_models_dir_from_env_reads_the_shell_variable():
    environ_set_by_desktop_shell = {MODELS_DIR_ENV: _APP_DIR}

    assert models_dir_from_env(environ_set_by_desktop_shell) == _APP_DIR


def test_models_dir_from_env_is_none_when_absent_or_blank():
    environ_without_variable = {}
    environ_with_blank_variable = {MODELS_DIR_ENV: "  "}

    assert models_dir_from_env(environ_without_variable) is None
    assert models_dir_from_env(environ_with_blank_variable) is None


def test_forget_removes_only_the_given_download(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")
    store.mark_downloaded("ministral-3:3b", _APP_DIR)
    store.mark_downloaded("ministral-3:3b", None)

    store.forget("ministral-3:3b", None)

    assert store.was_downloaded_by_opportune("ministral-3:3b", None) is False
    assert store.was_downloaded_by_opportune("ministral-3:3b", _APP_DIR) is True


def test_forget_unknown_download_does_nothing(tmp_path):
    origin_file = tmp_path / "llm-model-origin.json"
    store = ModelOriginStore(origin_file)

    store.forget("ministral-3:3b", _APP_DIR)

    assert not origin_file.exists()


def test_fingerprint_is_kept_with_the_download(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")

    store.mark_downloaded("ministral-3:3b", None, "2026-11-10T10:00:00Z")

    assert store.fingerprint_of("ministral-3:3b", None) == "2026-11-10T10:00:00Z"


def test_fingerprint_is_none_for_unknown_download(tmp_path):
    store = ModelOriginStore(tmp_path / "llm-model-origin.json")

    assert store.fingerprint_of("ministral-3:3b", None) is None


def test_new_download_at_same_place_replaces_the_fingerprint(tmp_path):
    origin_file = tmp_path / "llm-model-origin.json"
    store = ModelOriginStore(origin_file)
    store.mark_downloaded("ministral-3:3b", None, "2026-11-10T10:00:00Z")

    store.mark_downloaded("ministral-3:3b", None, "2026-12-01T09:30:00Z")

    assert store.fingerprint_of("ministral-3:3b", None) == "2026-12-01T09:30:00Z"
    assert origin_file.read_text(encoding="utf-8").count("ministral-3:3b") == 1
