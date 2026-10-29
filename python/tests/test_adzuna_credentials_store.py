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


def test_resolve_prefers_stored_credentials_over_env(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "adzuna.json")
    store.save("stored-id", "stored-key")

    resolved = resolve_adzuna_credentials(
        store, {"ADZUNA_APP_ID": "env-id", "ADZUNA_APP_KEY": "env-key"}
    )

    assert resolved == AdzunaCredentials(app_id="stored-id", app_key="stored-key")


def test_resolve_falls_back_to_env_when_store_empty(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "absent.json")

    resolved = resolve_adzuna_credentials(
        store, {"ADZUNA_APP_ID": "env-id", "ADZUNA_APP_KEY": "env-key"}
    )

    assert resolved == AdzunaCredentials(app_id="env-id", app_key="env-key")


def test_resolve_raises_when_neither_store_nor_env(tmp_path):
    store = AdzunaCredentialsStore(tmp_path / "absent.json")

    with pytest.raises(AdzunaAuthError):
        resolve_adzuna_credentials(store, {})
