"""Tests de la résolution des assets du front compilé (OPP-191)."""

from pathlib import Path

from api.frontend_assets import (
    content_type_for,
    frontend_dist_dir,
    resolve_static_file,
)


def _make_dist(tmp_path: Path) -> Path:
    """Fabrique un faux ``dist`` : index.html + un asset avec extension."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>")
    (dist / "assets" / "index-abc.js").write_text("console.log(1)")
    return dist


def test_root_path_serves_index(tmp_path):
    dist = _make_dist(tmp_path)

    assert resolve_static_file(dist, "/") == dist / "index.html"


def test_existing_asset_is_served_as_is(tmp_path):
    dist = _make_dist(tmp_path)

    assert resolve_static_file(dist, "/assets/index-abc.js") == dist / "assets" / "index-abc.js"


def test_query_string_is_ignored(tmp_path):
    dist = _make_dist(tmp_path)

    assert resolve_static_file(dist, "/assets/index-abc.js?v=2") == dist / "assets" / "index-abc.js"


def test_client_route_without_extension_falls_back_to_index(tmp_path):
    dist = _make_dist(tmp_path)

    assert resolve_static_file(dist, "/runs/42") == dist / "index.html"


def test_missing_asset_with_extension_is_not_found(tmp_path):
    dist = _make_dist(tmp_path)

    assert resolve_static_file(dist, "/assets/vieux.js") is None


def test_path_traversal_is_rejected(tmp_path):
    dist = _make_dist(tmp_path)
    (tmp_path / "secret.txt").write_text("secret")

    assert resolve_static_file(dist, "/../secret.txt") is None


def test_dist_dir_override_wins_when_directory_exists(tmp_path, monkeypatch):
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("OPPORTUNE_FRONTEND_DIST", str(dist))

    assert frontend_dist_dir() == dist


def test_dist_dir_override_missing_directory_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("OPPORTUNE_FRONTEND_DIST", str(tmp_path / "absent"))

    assert frontend_dist_dir() is None


def test_js_is_served_as_javascript_regardless_of_platform():
    """Un module ES doit être servi en ``text/javascript`` (jamais ``text/plain`` : refus navigateur).

    Régression du piège ``mimetypes`` sous Windows (registre → ``.js`` = ``text/plain``).
    """
    assert content_type_for("index-abc.js") == "text/javascript"


def test_css_is_served_as_css():
    assert content_type_for("index-abc.css") == "text/css"


def test_unknown_extension_falls_back_to_octet_stream():
    assert content_type_for("archive.xyzunknown") == "application/octet-stream"
