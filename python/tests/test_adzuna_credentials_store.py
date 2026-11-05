"""Tests du stockage local des identifiants Adzuna (OPP-222)."""

import json

import pytest

from app.adzuna_client import AdzunaAuthError, AdzunaCredentials
from app.adzuna_credentials_store import (
    AdzunaCredentialsStore,
    resolve_adzuna_credentials,
)


def test_save_then_load_round_trips_credentials(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")

    store.save("my-id", "my-key")

    assert store.load() == AdzunaCredentials(app_id="my-id", app_key="my-key")


def test_load_returns_none_when_file_absent(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "absent.json")

    loaded = store.load()

    assert loaded is None


def test_load_returns_none_on_corrupt_json(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{ pas du json", encoding="utf-8")
    store = AdzunaCredentialsStore(path)

    loaded = store.load()

    assert loaded is None


def test_load_returns_none_when_a_field_is_empty(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"app_id": "a", "app_key": ""}), encoding="utf-8")
    store = AdzunaCredentialsStore(path)

    loaded = store.load()

    assert loaded is None


def test_save_creates_parent_directory(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "sous" / "dossier" / "adzuna.json")

    store.save("a", "k")

    assert store.is_configured()


def test_save_restricts_file_permissions_to_owner(tmp_path):
    path = tmp_path / "adzuna.json"
    store = AdzunaCredentialsStore(path)

    store.save("a", "k")

    assert (path.stat().st_mode & 0o777) == 0o600


@pytest.mark.parametrize("app_id,app_key", [("", "k"), ("a", ""), ("  ", "k")])
def test_save_rejects_empty_credentials(tmp_path, app_id, app_key):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")

    with pytest.raises(ValueError):
        store.save(app_id, app_key)


def test_resolve_returns_the_stored_credentials(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")
    store.save("stored-id", "stored-key")

    resolved = resolve_adzuna_credentials(store)

    assert resolved == AdzunaCredentials(app_id="stored-id", app_key="stored-key")


def test_resolve_ignores_the_environment_when_nothing_is_stored(tmp_path, monkeypatch):
    store = AdzunaCredentialsStore(tmp_path / "absent.json")
    monkeypatch.setenv("ADZUNA_APP_ID", "env-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "env-key")

    with pytest.raises(AdzunaAuthError, match="Réglages"):
        resolve_adzuna_credentials(store)


def test_clear_removes_stored_credentials(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")
    store.save("my-id", "my-key")

    store.clear()

    assert store.load() is None


def test_clear_is_noop_when_file_absent(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "absent.json")

    store.clear()  # ne doit pas lever

    assert store.load() is None


def test_default_path_honours_data_dir(tmp_path):
    from app.adzuna_credentials_store import default_credentials_path

    assert default_credentials_path(tmp_path).parent == tmp_path
