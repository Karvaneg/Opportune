"""Isolation des réglages (clés Adzuna, flux RSS) par espace (OPP-195).

``assemble_api`` reçoit un ``settings_dir`` par espace : réel et démo écrivent dans des dossiers
différents, donc les clés/flux saisis dans l'un ne fuitent pas dans l'autre. On monte deux API
sur des dossiers temporaires distincts et on vérifie qu'un réglage posé d'un côté reste invisible
de l'autre ; puis que ``clear`` (ce que fait « repartir de zéro ») remet bien l'espace à nu.
"""

from api.server import assemble_api, build_local_auth
from app.db import connect


def _api(settings_dir):
    return assemble_api(
        connect(":memory:"), build_local_auth(lambda: ["cand-1"]), settings_dir=settings_dir
    )


def test_adzuna_credentials_isolated_between_spaces(tmp_path):
    mine = _api(tmp_path / "mine")
    demo = _api(tmp_path / "demo")

    mine.adzuna_credentials.save("id", "key")

    assert mine.adzuna_credentials.is_configured() is True
    assert demo.adzuna_credentials.is_configured() is False


def test_rss_feeds_isolated_between_spaces(tmp_path):
    mine = _api(tmp_path / "mine")
    demo = _api(tmp_path / "demo")

    mine.rss_feeds.save(["https://a.example/feed"])

    assert mine.rss_feeds.is_configured() is True
    assert demo.rss_feeds.is_configured() is False


def test_clear_resets_a_space_settings(tmp_path):
    demo = _api(tmp_path / "demo")
    demo.adzuna_credentials.save("id", "key")
    demo.rss_feeds.save(["https://a.example/feed"])

    demo.adzuna_credentials.clear()
    demo.rss_feeds.clear()

    assert demo.adzuna_credentials.is_configured() is False
    assert demo.rss_feeds.is_configured() is False
