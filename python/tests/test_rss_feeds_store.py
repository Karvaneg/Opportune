"""Tests du stockage local des URLs de flux RSS (OPP-195)."""

import json

import pytest

from app.rss_feeds_store import RssFeedsStore


def test_save_then_load_round_trips_feeds(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")

    store.save(["https://example.com/a.rss", "http://example.org/b.xml"])

    assert store.load() == ["https://example.com/a.rss", "http://example.org/b.xml"]


def test_load_returns_empty_when_file_absent(tmp_path):
    store = RssFeedsStore(tmp_path / "absent.json")

    loaded = store.load()

    assert loaded == []


def test_load_returns_empty_on_corrupt_json(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{ pas du json", encoding="utf-8")
    store = RssFeedsStore(path)

    loaded = store.load()

    assert loaded == []


def test_save_trims_and_drops_non_http_entries(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")

    saved = store.save(["  https://ok.example/feed  ", "ftp://nope", "", "pas une url"])

    assert saved == ["https://ok.example/feed"]
    assert store.load() == ["https://ok.example/feed"]


def test_save_rejects_when_no_usable_url(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")

    with pytest.raises(ValueError):
        store.save(["", "ftp://nope", "mailto:x@y.z"])


def test_load_ignores_non_string_and_schemeless_entries(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps({"feeds": ["https://ok.example/feed", 42, "ftp://skip", None]}),
        encoding="utf-8",
    )
    store = RssFeedsStore(path)

    assert store.load() == ["https://ok.example/feed"]


def test_is_configured_reflects_presence_of_feeds(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")
    assert store.is_configured() is False

    store.save(["https://example.com/feed"])

    assert store.is_configured() is True


def test_clear_removes_stored_feeds(tmp_path):
    store = RssFeedsStore(tmp_path / "rss.json")
    store.save(["https://example.com/feed"])

    store.clear()

    assert store.load() == []


def test_clear_is_noop_when_file_absent(tmp_path):
    store = RssFeedsStore(tmp_path / "absent.json")

    store.clear()  # ne doit pas lever

    assert store.load() == []


def test_default_path_honours_data_dir(tmp_path):
    from app.rss_feeds_store import default_rss_feeds_path

    assert default_rss_feeds_path(tmp_path).parent == tmp_path
