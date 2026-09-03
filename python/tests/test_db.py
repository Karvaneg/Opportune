"""Tests de la configuration SQLite (OPP-072)."""

from app.db import DEFAULT_DB_PATH, connect, healthcheck


def test_connect_in_memory_and_healthcheck():
    conn = connect(":memory:")
    try:
        assert healthcheck(conn) is True
    finally:
        conn.close()


def test_row_factory_gives_named_access():
    conn = connect(":memory:")
    try:
        row = conn.execute("SELECT 1 AS n").fetchone()
        assert row["n"] == 1  # accès par nom → sqlite3.Row actif
    finally:
        conn.close()


def test_foreign_keys_enabled():
    conn = connect(":memory:")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_creates_parent_directory(tmp_path):
    db_file = tmp_path / "nested" / "opportune.db"
    conn = connect(str(db_file))
    try:
        assert db_file.parent.exists()
        assert db_file.exists()
    finally:
        conn.close()


def test_default_db_path_is_defined():
    assert isinstance(DEFAULT_DB_PATH, str) and DEFAULT_DB_PATH != ""
