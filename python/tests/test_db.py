"""Tests de la configuration SQLite (OPP-072)."""

from app.db import DEFAULT_DB_PATH, connect, database_path, healthcheck


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


def test_wal_and_busy_timeout_on_file_db(tmp_path):
    # Collecte asynchrone (OPP-170) : la base fichier doit être en WAL (lecteur + écrivain
    # concurrents) avec un busy_timeout non nul ; ``:memory:`` reste en mode mémoire.
    conn = connect(str(tmp_path / "opportune.db"))
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0
    finally:
        conn.close()
    mem = connect(":memory:")
    try:
        assert mem.execute("PRAGMA journal_mode").fetchone()[0].lower() == "memory"
    finally:
        mem.close()


def test_database_path_returns_file_for_file_db(tmp_path):
    # Permet d'ouvrir une 2e connexion sur la MÊME base (runner de collecte de fond, OPP-170).
    db_file = tmp_path / "opportune.db"
    conn = connect(str(db_file))
    try:
        assert database_path(conn) == str(db_file)
    finally:
        conn.close()


def test_database_path_is_none_for_in_memory():
    conn = connect(":memory:")
    try:
        assert database_path(conn) is None
    finally:
        conn.close()
