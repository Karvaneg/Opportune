"""Tests de la source RSS et de son intégration au socle de collecte (OPP-122).

Fetch injecté (aucun réseau) : on vérifie le mapping article → ``RawOffer`` (HTML nettoyé), le
parcours multi-flux, le plafond, la propagation d'erreur, et la chaîne via ``collect_offers``.
"""

import json

import pytest

from app.llm_client import MockLLMClient
from app.offer import Offer, compute_offer_id
from app.offer_collection import collect_offers
from app.rss_source import SOURCE_NAME, RssSource, _to_raw_offer, build_rss_source
from app.rss_feed import FeedItem
from app.url_fetch import UrlUnreachableError


def _feed(items_xml):
    return f"<rss version='2.0'><channel>{items_xml}</channel></rss>"


def _item(n, title="Dév Python", desc="Mission"):
    return (
        f"<item><title>{title}</title>"
        f"<link>https://x/{n}</link><description>{desc}</description></item>"
    )


class FakeFetch:
    """Fetch scriptable : map url -> XML, enregistre l'ordre des appels."""

    def __init__(self, by_url):
        self._by_url = dict(by_url)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self._by_url[url]


# --- mapping article → RawOffer ---------------------------------------------------------


def test_to_raw_offer_cleans_html_and_builds_header():
    item = FeedItem(
        title="Backend Python",
        link="https://x/1",
        summary="<p>Super poste <b>CDI</b> à Paris.</p>",
    )
    raw = _to_raw_offer(item)
    assert raw.source == SOURCE_NAME
    assert raw.url == "https://x/1"
    assert raw.raw_text.startswith("Backend Python")
    assert "Super poste" in raw.raw_text and "CDI" in raw.raw_text
    assert "<p>" not in raw.raw_text and "<b>" not in raw.raw_text  # HTML nettoyé


def test_to_raw_offer_without_summary_keeps_title_only():
    raw = _to_raw_offer(FeedItem(title="Titre seul", link="https://x/1", summary=""))
    assert raw.raw_text == "Titre seul"


# --- parcours des flux ------------------------------------------------------------------


def test_fetch_iterates_all_feeds_in_order():
    fetch = FakeFetch(
        {
            "https://a/rss": _feed(_item(1) + _item(2)),
            "https://b/rss": _feed(_item(3)),
        }
    )
    source = RssSource(["https://a/rss", "https://b/rss"], fetch=fetch)
    raws = list(source.fetch())
    assert [r.url for r in raws] == ["https://x/1", "https://x/2", "https://x/3"]
    assert fetch.calls == ["https://a/rss", "https://b/rss"]


def test_fetch_respects_max_offers_across_feeds():
    fetch = FakeFetch({"https://a/rss": _feed(_item(1) + _item(2) + _item(3))})
    raws = list(RssSource(["https://a/rss"], fetch=fetch, max_offers=2).fetch())
    assert len(raws) == 2


def test_fetch_stops_calling_feeds_once_cap_reached():
    fetch = FakeFetch(
        {"https://a/rss": _feed(_item(1) + _item(2)), "https://b/rss": _feed(_item(3))}
    )
    raws = list(RssSource(["https://a/rss", "https://b/rss"], fetch=fetch, max_offers=2).fetch())
    assert len(raws) == 2
    assert fetch.calls == ["https://a/rss"]  # 2e flux jamais appelé


def test_build_rss_source_drops_blank_urls():
    source = build_rss_source(["https://a/rss", "", "  "])
    assert source._feed_urls == ["https://a/rss"]


# --- propagation d'erreur (→ source_error du pipeline) ----------------------------------


def test_fetch_propagates_feed_error():
    def broken_fetch(url):
        raise UrlUnreachableError("502")

    with pytest.raises(UrlUnreachableError):
        list(RssSource(["https://a/rss"], fetch=broken_fetch).fetch())


# --- preuve d'intégration via le socle de collecte --------------------------------------


class FakeOfferStore:
    def __init__(self):
        self.offers: dict[str, Offer] = {}

    def save(self, offer: Offer) -> None:
        self.offers[offer.id] = offer

    def get(self, offer_id: str):
        return self.offers.get(offer_id)


def _analysis(title="Dév Python"):
    return json.dumps(
        {
            "title": title,
            "company": "Acme",
            "location": "Paris",
            "seniority": "Senior",
            "contract_type": "cdi",
            "summary": "Backend.",
            "skills": ["Python"],
            "attention_points": [],
        }
    )


def test_collect_offers_through_rss_source_normalizes_and_dedups():
    store = FakeOfferStore()
    fetch = FakeFetch({"https://a/rss": _feed(_item(1) + _item(2))})
    source = RssSource(["https://a/rss"], fetch=fetch)

    report = collect_offers(source, client=MockLLMClient([_analysis("A"), _analysis("B")]), store=store)

    assert report.collected == 2
    assert report.stored == 2
    assert report.source_error is None
    raw = _to_raw_offer(FeedItem(title="Dév Python", link="https://x/1", summary="Mission"))
    assert compute_offer_id(SOURCE_NAME, raw.url, raw.raw_text) in store.offers


def test_collect_offers_dedups_same_rss_item_without_second_llm_call():
    store = FakeOfferStore()
    fetch = FakeFetch({"https://a/rss": _feed(_item(1) + _item(1))})
    report = collect_offers(
        RssSource(["https://a/rss"], fetch=fetch), client=MockLLMClient([_analysis()]), store=store
    )
    assert report.stored == 1
    assert report.duplicates == 1
