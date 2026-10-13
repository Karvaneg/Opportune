"""Tests spécifiques au runner RSS (OPP-122).

Le lancement de passe et le rendu du bilan sont couverts par ``test_collection_runner`` ; ici
on teste la résolution des flux (options vs environnement) et le code de sortie sans flux.
"""

from app.rss_runner import _feeds_from, main


class _Args:
    def __init__(self, feed):
        self.feed = feed


def test_feeds_from_prefers_cli_options():
    args = _Args(["https://a/rss", "https://b/rss"])
    assert _feeds_from(args, {"RSS_FEED_URLS": "https://z/ignored"}) == [
        "https://a/rss",
        "https://b/rss",
    ]


def test_feeds_from_falls_back_to_env_split_on_separators():
    args = _Args([])
    env = {"RSS_FEED_URLS": "https://a/rss, https://b/rss;https://c/rss"}
    assert _feeds_from(args, env) == ["https://a/rss", "https://b/rss", "https://c/rss"]


def test_feeds_from_empty_when_nothing_provided():
    assert _feeds_from(_Args([]), {}) == []


def test_main_returns_1_without_feeds(monkeypatch, capsys):
    monkeypatch.delenv("RSS_FEED_URLS", raising=False)
    assert main([]) == 1
    assert "Aucun flux" in capsys.readouterr().out


def test_main_returns_1_when_scrape_extra_missing(monkeypatch, capsys):
    # Flux fourni mais extra 'scrape' absent : on échoue vite, avant tout réseau/LLM/DB.
    monkeypatch.setattr("app.rss_runner._scrape_extra_missing", lambda: True)
    assert main(["--feed", "https://exemple.fr/offres.rss"]) == 1
    assert "scrape" in capsys.readouterr().out
