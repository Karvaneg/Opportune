"""Tests de l'intake d'offre par URL (OPP-148).

Aucun réseau ni bs4 réel : fetch et extract sont injectés ; le LLM et le dépôt sont faux.
"""

import pytest

from app.llm_client import MockLLMClient
from app.offer_store import OfferStore
from app.db import connect
from app.offer_url_intake import intake_offer_from_url
from app.url_fetch import EmptyContentError, HtmlDocument, UrlUnreachableError

# Analyse LLM minimale valide (cf. OfferAnalysis.from_* attendu par analyze_offer).
_ANALYSIS = (
    '{"title": "Développeur Python", "company": "Acme", "location": "Paris", '
    '"contract_type": "CDI", "seniority": "Senior", "skills": ["Python"], '
    '"summary": "Backend data.", "attention_points": []}'
)


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield OfferStore(conn)
    conn.close()


def _fetch_ok(url):
    return HtmlDocument(url=url, html="<html><body>Offre Python</body></html>")


def test_intake_from_url_happy_path(store):
    client = MockLLMClient([_ANALYSIS])
    offer = intake_offer_from_url(
        "https://example.com/o",
        source="example.com",
        client=client,
        store=store,
        fetch=_fetch_ok,
        extract=lambda html: "Développeur Python — CDI Paris, stack Python/SQL.",
    )
    assert offer.title == "Développeur Python"
    assert offer.url == "https://example.com/o"
    assert offer.source == "example.com"
    assert store.get(offer.id) is not None


def test_intake_from_url_propagates_fetch_error(store):
    def fetch(url):
        raise UrlUnreachableError("404")

    with pytest.raises(UrlUnreachableError):
        intake_offer_from_url(
            "https://example.com/o", source="s", client=MockLLMClient([_ANALYSIS]),
            store=store, fetch=fetch, extract=lambda html: "x",
        )


def test_intake_from_url_empty_extraction_raises(store):
    with pytest.raises(EmptyContentError):
        intake_offer_from_url(
            "https://example.com/o", source="s", client=MockLLMClient([_ANALYSIS]),
            store=store, fetch=_fetch_ok, extract=lambda html: "   ",
        )
    # Rien n'a été persisté : page vide = échec de collecte, pas une offre vide.
    assert store.count() == 0
