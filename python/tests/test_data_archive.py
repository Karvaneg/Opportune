"""Tests de l'archive d'export / import des données (OPP-232), sans réseau."""

import io
import json
import zipfile

import pytest

from app import data_archive
from app.data_archive import DataArchiveError, build_archive, restore_archive
from app.database_schema import ensure_schema
from app.db import connect
from app.offer_store import OfferStore


def _db_with_rows(path, values):
    conn = connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS notes (value TEXT)")
    conn.executemany("INSERT INTO notes VALUES (?)", [(v,) for v in values])
    conn.commit()
    return conn


def _notes(conn):
    return [row[0] for row in conn.execute("SELECT value FROM notes ORDER BY value")]


def _settings(tmp_path, name):
    folder = tmp_path / name
    folder.mkdir()
    return [folder / "adzuna_credentials.json", folder / "rss_feeds.json", folder / "ats.json"]


def _archive(tmp_path, *, values=("a", "b"), rss=b'{"feeds": ["https://x/f"]}', app_version="1.0.0"):
    source = _db_with_rows(tmp_path / "source.db", values)
    files = _settings(tmp_path, "source-settings")
    files[0].write_bytes(b'{"app_id": "id", "app_key": "key"}')
    if rss is not None:
        files[1].write_bytes(rss)
    content = build_archive(source, files, app_version=app_version, exported_at="2026-11-05T10:00:00")
    source.close()
    return content


def _restore(content, conn, files, app_version="1.0.0"):
    restore_archive(content, conn, files, app_version=app_version, ensure_schema=ensure_schema)


def test_restore_replaces_database_and_settings(tmp_path):
    content = _archive(tmp_path)
    target = _db_with_rows(tmp_path / "target.db", ["ancienne"])
    files = _settings(tmp_path, "target-settings")
    files[2].write_bytes(b'{"companies": []}')

    _restore(content, target, files)

    assert _notes(target) == ["a", "b"]
    assert files[0].read_bytes() == b'{"app_id": "id", "app_key": "key"}'
    assert json.loads(files[1].read_bytes()) == {"feeds": ["https://x/f"]}
    assert not files[2].exists()


def test_restore_upgrades_the_schema_of_an_older_database(tmp_path):
    content = _archive(tmp_path)
    target = connect(str(tmp_path / "target.db"))

    _restore(content, target, _settings(tmp_path, "target-settings"))

    assert OfferStore(target).list_all() == []


def test_archive_contains_a_manifest_with_the_app_version(tmp_path):
    content = _archive(tmp_path, app_version="1.2.3")

    manifest = json.loads(zipfile.ZipFile(io.BytesIO(content)).read("manifest.json"))

    assert manifest["format"] == "opportune-export"
    assert manifest["app_version"] == "1.2.3"


def _zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "content",
    [
        b"pas un zip",
        _zip({"autre.txt": "x"}),
        _zip({"manifest.json": json.dumps({"format": "autre"})}),
        _zip({"manifest.json": json.dumps({"format": "opportune-export", "format_version": 1, "app_version": "1.0.0"})}),
        _zip(
            {
                "manifest.json": json.dumps({"format": "opportune-export", "format_version": 1, "app_version": "1.0.0"}),
                "opportune.db": b"pas une base sqlite",
            }
        ),
    ],
)
def test_invalid_archives_are_refused_without_changing_anything(tmp_path, content):
    target = _db_with_rows(tmp_path / "target.db", ["ancienne"])
    files = _settings(tmp_path, "target-settings")
    files[1].write_bytes(b"inchange")

    with pytest.raises(DataArchiveError):
        _restore(content, target, files)

    assert _notes(target) == ["ancienne"]
    assert files[1].read_bytes() == b"inchange"


def test_archive_from_a_newer_app_version_is_refused(tmp_path):
    content = _archive(tmp_path, app_version="2.0.0")
    target = _db_with_rows(tmp_path / "target.db", ["ancienne"])

    with pytest.raises(DataArchiveError, match="plus récent"):
        _restore(content, target, _settings(tmp_path, "target-settings"), app_version="1.0.0")

    assert _notes(target) == ["ancienne"]


def test_archive_from_a_dev_build_is_accepted(tmp_path):
    content = _archive(tmp_path, app_version="1.0.0-dev")
    target = _db_with_rows(tmp_path / "target.db", ["ancienne"])

    _restore(content, target, _settings(tmp_path, "target-settings"), app_version="1.1.0rc1")

    assert _notes(target) == ["a", "b"]


def test_database_too_large_once_decompressed_is_refused(tmp_path, monkeypatch):
    content = _archive(tmp_path)
    target = _db_with_rows(tmp_path / "target.db", ["ancienne"])
    monkeypatch.setattr(data_archive, "MAX_DATABASE_BYTES", 10)

    with pytest.raises(DataArchiveError, match="trop volumineuse"):
        _restore(content, target, _settings(tmp_path, "target-settings"))

    assert _notes(target) == ["ancienne"]


def test_failed_settings_write_puts_back_the_previous_data(tmp_path, monkeypatch):
    content = _archive(tmp_path)
    target = _db_with_rows(tmp_path / "target.db", ["ancienne"])
    files = _settings(tmp_path, "target-settings")
    files[1].write_bytes(b"anciens flux")
    files[2].write_bytes(b"anciennes entreprises")
    real_write = data_archive._write_private

    def write_then_fail(path, data):
        if path == files[1]:
            raise OSError("disque plein")
        real_write(path, data)

    monkeypatch.setattr(data_archive, "_write_private", write_then_fail)

    with pytest.raises(OSError, match="disque plein"):
        _restore(content, target, files)

    assert _notes(target) == ["ancienne"]
    assert not files[0].exists()
    assert files[1].read_bytes() == b"anciens flux"
    assert files[2].read_bytes() == b"anciennes entreprises"
