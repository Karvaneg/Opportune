"""Tests de la source Adzuna et de son intégration au socle de collecte (OPP-120).

Deux niveaux : (1) pagination et mapping offre → ``RawOffer`` avec un **faux client** ;
(2) **preuve d'intégration** bout en bout via ``collect_offers`` avec le vrai client + un
transport injecté — les offres ressortent normalisées et dédoublonnées par le socle, sans réseau.
"""

import json

import pytest

from app.adzuna_client import (
    AdzunaClient,
    AdzunaCredentials,
    AdzunaQuotaError,
    HttpResponse,
    SearchPage,
)
from app.adzuna_source import (
    SOURCE_NAME,
    AdzunaSource,
    _raw_text,
    build_adzuna_source,
)
from app.llm_client import MockLLMClient
from app.offer import Offer, compute_offer_id
from app.offer_collection import collect_offers


class FakeClient:
    """Faux client : pages de recherche scriptées, appels enregistrés."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.search_calls = []

    def search(self, *, page, results_per_page, extra_params=None):
        self.search_calls.append({"page": page, "rpp": results_per_page, "extra": extra_params})
        return self._pages.pop(0)


def _offer(offer_id, title="Dév", description="desc"):
    return {
        "id": offer_id,
        "title": title,
        "description": description,
        "company": {"display_name": "Acme"},
        "location": {"display_name": "Paris, Île-de-France"},
        "contract_type": "permanent",
        "contract_time": "full_time",
        "redirect_url": f"https://www.adzuna.fr/details/{offer_id}",
    }


# --- mapping offre → RawOffer -----------------------------------------------------------


def test_raw_text_composes_header_location_contract_and_description():
    text = _raw_text(_offer("1", title="Backend Python", description="Mission backend."))
    assert "Backend Python — Acme" in text
    assert "Lieu : Paris, Île-de-France" in text
    assert "permanent full_time" in text
    assert "Mission backend." in text


def test_raw_text_tolerates_missing_fields():
    assert _raw_text({"title": "Titre seul"}) == "Titre seul"


def test_to_raw_offer_uses_redirect_url_as_dedup_key():
    source = AdzunaSource(FakeClient([SearchPage(offers=(_offer("77"),), total=1)]))
    (raw,) = list(source.fetch())
    assert raw.url == "https://www.adzuna.fr/details/77"
    assert raw.source == SOURCE_NAME


# --- pagination -------------------------------------------------------------------------


def test_fetch_defaults_to_permanent_filter():
    client = FakeClient([SearchPage(offers=(), total=0)])
    list(AdzunaSource(client).fetch())
    assert client.search_calls[0]["extra"] == {"permanent": "1"}


def test_fetch_can_lift_permanent_filter():
    client = FakeClient([SearchPage(offers=(), total=0)])
    list(AdzunaSource(client, permanent=False).fetch())
    assert client.search_calls[0]["extra"] is None


def test_fetch_merges_user_filters_with_permanent():
    client = FakeClient([SearchPage(offers=(), total=0)])
    list(AdzunaSource(client, filters={"what": "python"}).fetch())
    assert client.search_calls[0]["extra"] == {"what": "python", "permanent": "1"}


def test_fetch_advances_page_until_total():
    client = FakeClient(
        [
            SearchPage(offers=tuple(_offer(str(i)) for i in range(2)), total=3),
            SearchPage(offers=(_offer("2"),), total=3),
        ]
    )
    raws = list(AdzunaSource(client, page_size=2).fetch())
    assert [r.url.split("/")[-1] for r in raws] == ["0", "1", "2"]
    assert [c["page"] for c in client.search_calls] == [1, 2]


def test_fetch_stops_on_partial_page():
    client = FakeClient([SearchPage(offers=(_offer("0"),), total=999)])
    raws = list(AdzunaSource(client, page_size=2).fetch())
    assert len(raws) == 1
    assert len(client.search_calls) == 1


def test_fetch_stops_on_empty_page():
    client = FakeClient([SearchPage(offers=(), total=0)])
    assert list(AdzunaSource(client, page_size=2).fetch()) == []


def test_fetch_respects_max_offers_cap():
    # max_offers=3, page_size=2 → 1re page demande 2, 2e page ne demande qu'1 (reste), stop.
    client = FakeClient(
        [
            SearchPage(offers=tuple(_offer(str(i)) for i in range(2)), total=9999),
            SearchPage(offers=(_offer("2"),), total=9999),
        ]
    )
    raws = list(AdzunaSource(client, page_size=2, max_offers=3).fetch())
    assert len(raws) == 3
    assert client.search_calls[1]["rpp"] == 1  # reste borné au plafond


# --- propagation d'erreur (→ source_error du pipeline) ----------------------------------


def test_fetch_propagates_client_error_mid_iteration():
    class FlakyClient(FakeClient):
        def search(self, *, page, results_per_page, extra_params=None):
            if page == 1:
                return SearchPage(offers=(_offer("0"), _offer("1")), total=99)
            raise AdzunaQuotaError("429")

    source = AdzunaSource(FlakyClient([]), page_size=2)
    gen = source.fetch()
    assert next(gen).url.endswith("/0")
    assert next(gen).url.endswith("/1")
    with pytest.raises(AdzunaQuotaError):
        next(gen)


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


def _real_client(pages):
    """Vrai ``AdzunaClient`` câblé sur un transport scripté (une ``HttpResponse`` par page)."""
    responses = [
        HttpResponse(200, json.dumps({"count": total, "results": offers})) for offers, total in pages
    ]

    def transport(url):
        return responses.pop(0)

    return AdzunaClient(AdzunaCredentials(app_id="a", app_key="k"), transport=transport)


def test_collect_offers_through_adzuna_source_normalizes_and_dedups():
    store = FakeOfferStore()
    client = _real_client([([_offer("a"), _offer("b")], 2)])
    source = AdzunaSource(client, page_size=50)

    report = collect_offers(source, client=MockLLMClient([_analysis("A"), _analysis("B")]), store=store)

    assert report.collected == 2
    assert report.stored == 2
    assert report.source_error is None
    expected = compute_offer_id(SOURCE_NAME, _offer("a")["redirect_url"], _raw_text(_offer("a")))
    assert expected in store.offers


def test_collect_offers_dedups_same_adzuna_offer_without_second_llm_call():
    store = FakeOfferStore()
    client = _real_client([([_offer("a"), _offer("a")], 2)])
    report = collect_offers(AdzunaSource(client), client=MockLLMClient([_analysis()]), store=store)
    assert report.stored == 1
    assert report.duplicates == 1


def test_collect_offers_records_source_error_on_quota():
    responses = [HttpResponse(429, "")]

    def transport(url):
        return responses.pop(0)

    client = AdzunaClient(AdzunaCredentials(app_id="a", app_key="k"), transport=transport)
    report = collect_offers(AdzunaSource(client), client=MockLLMClient([]), store=FakeOfferStore())

    assert report.collected == 0
    assert report.source_error is not None
    assert "429" in report.source_error


def test_build_adzuna_source_from_credentials():
    source = build_adzuna_source(AdzunaCredentials(app_id="a", app_key="k"))
    assert isinstance(source, AdzunaSource)
