"""Tests de la mise à niveau du schéma d'un espace (OPP-232, OPP-243)."""

from api.server import assemble_api, build_local_auth
from app.database_schema import ensure_schema
from app.db import connect


def _tables(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def test_ensure_schema_drops_obsolete_submissions_table():
    conn = connect(":memory:")
    conn.execute("CREATE TABLE submissions (recommendation_id TEXT PRIMARY KEY)")

    ensure_schema(conn)

    assert "submissions" not in _tables(conn)


def test_ensure_schema_without_obsolete_table_creates_store_tables():
    conn = connect(":memory:")

    ensure_schema(conn)

    assert {"offers", "candidate_offers"} <= _tables(conn)


def test_assemble_api_drops_obsolete_submissions_table_at_boot(tmp_path):
    conn = connect(str(tmp_path / "opportune.db"))
    conn.execute("CREATE TABLE submissions (recommendation_id TEXT PRIMARY KEY)")

    assemble_api(conn, build_local_auth(lambda: []), settings_dir=tmp_path / "settings")

    assert "submissions" not in _tables(conn)
