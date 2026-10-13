"""Tests de la source France Travail et de son intégration au socle de collecte (OPP-120).

Deux niveaux : (1) la pagination et le mapping offre → ``RawOffer`` avec un **faux client**
(isolation pure de la logique de source) ; (2) une **preuve d'intégration** bout en bout à
travers ``collect_offers`` avec le vrai client + un transport injecté — les offres CDI de
l'API ressortent normalisées et dédoublonnées par le socle, sans réseau.
"""

import json

import pytest

from app.france_travail_client import (
    FranceTravailClient,
    FranceTravailCredentials,
    FranceTravailQuotaError,
    HttpResponse,
    SearchPage,
)
from app.france_travail_source import (
    SOURCE_NAME,
    FranceTravailSource,
    _raw_text,
    build_france_travail_source,
    _offer_url,
)
from app.llm_client import MockLLMClient
from app.offer import Offer, compute_offer_id
from app.offer_collection import collect_offers


class FakeClient:
    """Faux client : jeton figé + pages de recherche scriptées, appels enregistrés."""

    def __init__(self, pages):
        self._pages = list(pages)
        self.search_calls = []
        self.token_calls = 0

    def fetch_token(self):
        self.token_calls += 1
        return "tok"

    def search(self, *, token, start, end, extra_params=None):
        self.search_calls.append({"start": start, "end": end, "extra": extra_params})
        return self._pages.pop(0)


def _offer(offer_id, intitule="Dév", description="desc"):
    return {
        "id": offer_id,
        "intitule": intitule,
        "description": description,
        "entreprise": {"nom": "Acme"},
        "lieuTravail": {"libelle": "Paris (75)"},
        "typeContrat": "CDI",
        "typeContratLibelle": "Contrat à durée indéterminée",
    }


# --- mapping offre → RawOffer -----------------------------------------------------------


def test_raw_text_composes_header_location_contract_and_description():
    text = _raw_text(_offer("1", intitule="Backend Python", description="Mission backend."))
    assert "Backend Python — Acme" in text
    assert "Lieu : Paris (75)" in text
    assert "Contrat à durée indéterminée" in text
    assert "Mission backend." in text


def test_raw_text_tolerates_missing_fields():
    text = _raw_text({"intitule": "Titre seul"})
    assert text == "Titre seul"


def test_offer_url_prefers_origin_link():
    offer = _offer("1")
    offer["origineOffre"] = {"urlOrigine": "https://partenaire.example/offre/1"}
    assert _offer_url(offer) == "https://partenaire.example/offre/1"


def test_offer_url_falls_back_to_candidate_detail_url():
    assert _offer_url(_offer("77abc")).endswith("/detail/77abc")


def test_offer_url_empty_without_id_or_link():
    assert _offer_url({"intitule": "x"}) == ""


# --- pagination -------------------------------------------------------------------------


def test_fetch_stops_at_announced_total_across_pages():
    source = FranceTravailSource(
        FakeClient(
            [
                SearchPage(offers=tuple(_offer(str(i)) for i in range(2)), total=3),
                SearchPage(offers=(_offer("2"),), total=3),
            ]
        ),
        page_size=2,
    )

    raws = list(source.fetch())

    assert [r.url.split("/")[-1] for r in raws] == ["0", "1", "2"]
    assert all(r.source == SOURCE_NAME for r in raws)


def test_fetch_advances_range_by_page_size():
    client = FakeClient(
        [
            SearchPage(offers=tuple(_offer(str(i)) for i in range(2)), total=4),
            SearchPage(offers=tuple(_offer(str(i)) for i in range(2, 4)), total=4),
        ]
    )
    source = FranceTravailSource(client, page_size=2)

    list(source.fetch())

    assert client.search_calls[0]["start"] == 0 and client.search_calls[0]["end"] == 1
    assert client.search_calls[1]["start"] == 2 and client.search_calls[1]["end"] == 3


def test_fetch_stops_on_partial_page():
    client = FakeClient([SearchPage(offers=(_offer("0"),), total=999)])
    source = FranceTravailSource(client, page_size=2)

    raws = list(source.fetch())

    assert len(raws) == 1
    assert len(client.search_calls) == 1  # page partielle → pas de page suivante demandée


def test_fetch_stops_on_empty_page():
    client = FakeClient([SearchPage(offers=(), total=0)])
    source = FranceTravailSource(client, page_size=2)

    assert list(source.fetch()) == []


def test_fetch_respects_max_offers_window():
    # max_offers=3, page_size=2 → première page 0-1, seconde bornée à 2-2 (pas 2-3).
    client = FakeClient(
        [
            SearchPage(offers=tuple(_offer(str(i)) for i in range(2)), total=9999),
            SearchPage(offers=(_offer("2"),), total=9999),
        ]
    )
    source = FranceTravailSource(client, page_size=2, max_offers=3)

    list(source.fetch())

    assert client.search_calls[1]["end"] == 2  # borné à la fenêtre, pas start+page_size-1


def test_fetch_never_requests_range_outside_api_window():
    # Garde-fou OPP-120 : pages pleines à l'infini (total immense) → la source ne doit JAMAIS
    # demander un range dont le premier élément dépasse 1000 ni le second 1149 (sinon 400).
    class FullPagesClient(FakeClient):
        def search(self, *, token, start, end, extra_params=None):
            self.search_calls.append({"start": start, "end": end, "extra": extra_params})
            return SearchPage(offers=tuple(_offer(str(start + i)) for i in range(150)), total=10_000)

    source = FranceTravailSource(FullPagesClient([]), page_size=150)

    list(source.fetch())
    calls = source._client.search_calls

    assert calls  # au moins une page demandée
    assert all(call["start"] <= 1000 for call in calls)
    assert all(call["end"] <= 1149 for call in calls)


def test_fetch_forwards_filters_to_search():
    client = FakeClient([SearchPage(offers=(), total=0)])
    source = FranceTravailSource(client, filters={"codeROME": "M1805"})

    list(source.fetch())

    assert client.search_calls[0]["extra"] == {"codeROME": "M1805"}


# --- propagation d'erreur (→ source_error du pipeline) ----------------------------------


def test_fetch_propagates_client_error_mid_iteration():
    class FlakyClient(FakeClient):
        def search(self, *, token, start, end, extra_params=None):
            if start == 0:
                return SearchPage(offers=(_offer("0"), _offer("1")), total=99)
            raise FranceTravailQuotaError("429")

    source = FranceTravailSource(FlakyClient([]), page_size=2)
    gen = source.fetch()
    assert next(gen).url.endswith("/0")
    assert next(gen).url.endswith("/1")
    with pytest.raises(FranceTravailQuotaError):
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
    """Vrai ``FranceTravailClient`` câblé sur un transport scripté (token puis pages)."""
    responses = [HttpResponse(200, {}, json.dumps({"access_token": "tok"}))]
    for offers, total in pages:
        body = json.dumps({"resultats": offers})
        last = len(offers) - 1 if offers else 0
        responses.append(HttpResponse(200, {"Content-Range": f"offres 0-{last}/{total}"}, body))

    def transport(method, url, headers, body):
        return responses.pop(0)

    return FranceTravailClient(
        FranceTravailCredentials(client_id="cid", client_secret="secret"), transport=transport
    )


def test_collect_offers_through_france_travail_source_normalizes_and_dedups():
    store = FakeOfferStore()
    client = _real_client([([_offer("a"), _offer("b")], 2)])
    source = FranceTravailSource(client, page_size=150)

    report = collect_offers(source, client=MockLLMClient([_analysis("A"), _analysis("B")]), store=store)

    assert report.collected == 2
    assert report.stored == 2
    assert report.duplicates == 0
    assert report.source_error is None
    assert len(store.offers) == 2
    # L'URL de détail France Travail est bien la clé de dédup persistée.
    expected = compute_offer_id(SOURCE_NAME, _offer_url(_offer("a")), _raw_text(_offer("a")))
    assert expected in store.offers


def test_collect_offers_dedups_same_france_travail_offer_without_second_llm_call():
    store = FakeOfferStore()
    client = _real_client([([_offer("a"), _offer("a")], 2)])
    # Une seule réponse LLM scriptée : si le doublon appelait le LLM, ça lèverait (pop vide).
    report = collect_offers(
        FranceTravailSource(client), client=MockLLMClient([_analysis()]), store=store
    )

    assert report.collected == 2
    assert report.stored == 1
    assert report.duplicates == 1


def test_collect_offers_records_source_error_on_quota():
    store = FakeOfferStore()
    responses = [
        HttpResponse(200, {}, json.dumps({"access_token": "tok"})),
        HttpResponse(429, {}, ""),
    ]

    def transport(method, url, headers, body):
        return responses.pop(0)

    client = FranceTravailClient(
        FranceTravailCredentials(client_id="c", client_secret="s"), transport=transport
    )
    report = collect_offers(FranceTravailSource(client), client=MockLLMClient([]), store=store)

    assert report.collected == 0
    assert report.source_error is not None
    assert "429" in report.source_error


def test_build_france_travail_source_from_env():
    source = build_france_travail_source(
        {"FRANCE_TRAVAIL_CLIENT_ID": "cid", "FRANCE_TRAVAIL_CLIENT_SECRET": "secret"}
    )
    assert isinstance(source, FranceTravailSource)
