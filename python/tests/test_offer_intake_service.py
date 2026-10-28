"""Tests de l'intégration de l'analyse LLM dans le cycle d'une offre (OPP-037).

Faux LLM (``MockLLMClient``) + fausse persistance (``FakeOfferStore``) : ni réseau,
ni SQLite.
"""

import json

import pytest

from app.llm_client import LLMError, MockLLMClient
from app.offer import Offer
from app.offer_analysis import OfferAnalysisError
from app.offer_intake_service import intake_offer, intake_offer_enriched
from app.url_fetch import BlockedError, HtmlDocument

VALID_RESPONSE = json.dumps(
    {
        "title": "Développeur Python",
        "company": "Acme",
        "location": "Paris",
        "seniority": "Senior",
        "contract_type": "cdi",
        "summary": "Backend data.",
        "skills": ["Python", "python"],
        "attention_points": [],
    }
)

# Analyse sans aucune compétence (cas d'un extrait tronqué type snippet Adzuna).
NO_SKILLS_RESPONSE = json.dumps(
    {
        "title": "Développeur Web",
        "company": "WebCorp",
        "location": "Bordeaux",
        "seniority": "Non précisé",
        "contract_type": "cdi",
        "summary": "Poste de dev.",
        "skills": [],
        "attention_points": [],
    }
)


def _fetcher(html: str = "<html>offre complète</html>"):
    """Faux fetch qui enregistre les URL demandées et renvoie un HTML figé."""
    calls: list[str] = []

    def fetch(url: str) -> HtmlDocument:
        calls.append(url)
        return HtmlDocument(url=url, html=html)

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


class FakeOfferStore:
    """Fausse persistance en mémoire respectant le contrat ``OfferRepository``."""

    def __init__(self):
        self.offers: dict[str, Offer] = {}

    def save(self, offer: Offer) -> None:
        self.offers[offer.id] = offer

    def get(self, offer_id: str):
        return self.offers.get(offer_id)


def test_intake_analyzes_normalizes_and_persists():
    store = FakeOfferStore()
    offer = intake_offer(
        "Développeur Python backend",
        source="indeed", url="http://x", client=MockLLMClient([VALID_RESPONSE]), store=store,
    )
    assert offer.contract_type == "CDI"  # normalisé
    assert offer.skills == ["Python"]  # dédoublonné (et ancré au texte)
    assert store.get(offer.id) == offer  # bien persistée


def test_intake_drops_skills_absent_from_text():
    # Garde-fou anti-invention (OPP-213) : une compétence que le LLM renvoie mais qui
    # n'apparaît pas dans le texte de l'offre est écartée à la persistance.
    store = FakeOfferStore()
    hallucinated = json.dumps(
        {
            "title": "Lead Développeur React",
            "company": "SQLI",
            "location": "Paris",
            "seniority": "Senior",
            "contract_type": "cdi",
            "summary": "Agence digitale.",
            # Seul « React » figure dans le texte ; le reste est inventé par le modèle.
            "skills": ["React", "JavaScript", "AWS", "Docker"],
            "attention_points": [],
        }
    )
    offer = intake_offer(
        "Lead Développeur React — agence digitale spécialisée en React.",
        source="adzuna", url="http://x", client=MockLLMClient([hallucinated]), store=store,
    )
    assert offer.skills == ["React"]  # seule la compétence réellement présente survit


def test_intake_upserts_existing_offer():
    store = FakeOfferStore()
    client = MockLLMClient([VALID_RESPONSE, VALID_RESPONSE])
    first = intake_offer("t", source="indeed", url="http://x", client=client, store=store)
    second = intake_offer("t", source="indeed", url="http://x", client=client, store=store)
    assert first.id == second.id
    assert len(store.offers) == 1  # pas de doublon


def test_intake_upserts_despite_title_drift_when_url_present():
    # Le LLM reformule le titre à la seconde analyse : avec une url stable, l'id ne
    # doit pas changer et l'offre est mise à jour, pas dupliquée.
    store = FakeOfferStore()
    drifted = json.dumps({**json.loads(VALID_RESPONSE), "title": "Développeur Python H/F"})
    client = MockLLMClient([VALID_RESPONSE, drifted])
    first = intake_offer("t", source="indeed", url="http://x", client=client, store=store)
    second = intake_offer("t", source="indeed", url="http://x", client=client, store=store)
    assert first.id == second.id
    assert len(store.offers) == 1


def test_intake_upserts_despite_title_drift_without_url():
    # Scénario « Holis » : offre collée (pas d'url), le LLM reformule le titre entre
    # deux ingestions du MÊME texte. L'id étant dérivé du raw_text, l'offre est mise à
    # jour, pas dupliquée — c'est le correctif de dédup à l'intake.
    store = FakeOfferStore()
    drifted = json.dumps({**json.loads(VALID_RESPONSE), "title": "Développeur Python chez Acme"})
    client = MockLLMClient([VALID_RESPONSE, drifted])
    first = intake_offer("même texte collé", source="collée", client=client, store=store)
    second = intake_offer("même texte collé", source="collée", client=client, store=store)
    assert first.id == second.id
    assert len(store.offers) == 1  # pas de doublon malgré la dérive du titre


def test_intake_rejects_invalid_analysis_and_persists_nothing():
    store = FakeOfferStore()
    client = MockLLMClient(["pas du json"])
    with pytest.raises(OfferAnalysisError):
        intake_offer("t", source="indeed", client=client, store=store)
    assert store.offers == {}


def test_intake_propagates_llm_error():
    store = FakeOfferStore()
    client = MockLLMClient(error=LLMError("réseau"))
    with pytest.raises(LLMError):
        intake_offer("t", source="indeed", client=client, store=store)
    assert store.offers == {}


def test_intake_requires_source():
    store = FakeOfferStore()
    with pytest.raises(ValueError):
        intake_offer("t", source="  ", client=MockLLMClient([VALID_RESPONSE]), store=store)


# --- Enrichissement en secours (OPP-169) ------------------------------------


def test_enriched_fetches_full_text_when_no_skills():
    # Snippet → aucune compétence ; avec une url, on récupère la page complète et on
    # ré-analyse : l'offre persistée porte les compétences du second passage et le texte enrichi.
    store = FakeOfferStore()
    client = MockLLMClient([NO_SKILLS_RESPONSE, VALID_RESPONSE])
    fetch = _fetcher()
    extract = lambda html: "texte complet et riche en Python de l'offre"  # noqa: E731
    result = intake_offer_enriched(
        "snippet maigre", source="adzuna", url="http://x/offre",
        client=client, store=store, fetch=fetch, extract=extract,
    )
    assert result.offer.skills == ["Python"]  # issu de la ré-analyse du texte complet
    assert result.offer.raw_text == "texte complet et riche en Python de l'offre"
    assert result.enrichment_attempted is True
    assert result.enrichment_recovered is True
    assert fetch.calls == ["http://x/offre"]
    assert len(client.calls) == 2  # deux passes : snippet puis texte enrichi


def test_enriched_fetches_full_text_when_skills_all_unanchored():
    # OPP-213 : le snippet produit des compétences, mais toutes inventées (absentes du texte) →
    # l'ancrage les écarte → l'offre se retrouve sans skill ancrée, ce qui doit déclencher
    # l'enrichissement au même titre qu'une analyse sans aucune compétence (et non persister
    # une offre silencieusement vidée).
    store = FakeOfferStore()
    client = MockLLMClient([VALID_RESPONSE, VALID_RESPONSE])
    fetch = _fetcher()
    extract = lambda html: "texte complet et riche en Python de l'offre"  # noqa: E731
    result = intake_offer_enriched(
        # Le snippet ne mentionne pas « Python » : les skills du 1ᵉ passage ne s'ancrent pas.
        "snippet maigre sans techno", source="adzuna", url="http://x/offre",
        client=client, store=store, fetch=fetch, extract=extract,
    )
    assert result.offer.skills == ["Python"]  # récupérées via la page complète
    assert result.enrichment_attempted is True
    assert result.enrichment_recovered is True
    assert fetch.calls == ["http://x/offre"]
    assert len(client.calls) == 2  # la 2ᵉ passe a bien été déclenchée malgré des skills bruts


def test_enriched_skips_fetch_when_skills_present():
    # Cas courant : le snippet suffit → aucune récupération réseau, une seule passe LLM.
    store = FakeOfferStore()
    client = MockLLMClient([VALID_RESPONSE])
    fetch = _fetcher()
    result = intake_offer_enriched(
        "snippet suffisant mentionnant Python", source="adzuna", url="http://x/offre",
        client=client, store=store, fetch=fetch, extract=lambda h: "ignoré",
    )
    assert result.offer.skills == ["Python"]
    assert result.enrichment_attempted is False
    assert result.enrichment_recovered is False
    assert fetch.calls == []  # pas d'enrichissement déclenché
    assert len(client.calls) == 1


def test_enriched_skips_fetch_when_no_url():
    # Offre sans url (ex. collage) : rien à récupérer, l'analyse vide est conservée telle quelle.
    store = FakeOfferStore()
    client = MockLLMClient([NO_SKILLS_RESPONSE])
    fetch = _fetcher()
    result = intake_offer_enriched(
        "snippet", source="collée", url="", client=client, store=store,
        fetch=fetch, extract=lambda h: "jamais",
    )
    assert result.offer.skills == []
    assert result.enrichment_attempted is False
    assert fetch.calls == []
    assert len(client.calls) == 1


def test_enriched_falls_back_to_snippet_when_fetch_blocked():
    # Le fetch échoue (anti-bot 403) : on retombe sur l'analyse du snippet, l'offre est
    # tout de même persistée — l'enrichissement n'enlève jamais une offre du catalogue.
    store = FakeOfferStore()
    client = MockLLMClient([NO_SKILLS_RESPONSE])

    def fetch(url):
        raise BlockedError("403")

    result = intake_offer_enriched(
        "snippet", source="adzuna", url="http://x/offre", client=client, store=store,
        fetch=fetch, extract=lambda h: "jamais atteint",
    )
    assert result.offer.skills == []
    assert result.offer.raw_text == "snippet"  # texte initial conservé
    assert result.enrichment_attempted is True  # tentée…
    assert result.enrichment_recovered is False  # …mais rien récupéré (fetch bloqué)
    assert store.get(result.offer.id) is result.offer
    assert len(client.calls) == 1  # pas de seconde passe


def test_enriched_falls_back_when_extracted_text_empty():
    # Page récupérée mais aucun texte exploitable → pas de ré-analyse, on garde le snippet.
    store = FakeOfferStore()
    client = MockLLMClient([NO_SKILLS_RESPONSE])
    fetch = _fetcher()
    result = intake_offer_enriched(
        "snippet", source="adzuna", url="http://x/offre", client=client, store=store,
        fetch=fetch, extract=lambda h: "   ",
    )
    assert result.offer.skills == []
    assert result.offer.raw_text == "snippet"
    assert result.enrichment_attempted is True
    assert result.enrichment_recovered is False
    assert fetch.calls == ["http://x/offre"]
    assert len(client.calls) == 1


def test_enriched_falls_back_when_reanalysis_fails():
    # La ré-analyse du texte enrichi échoue (JSON invalide) : on conserve l'analyse du
    # snippet plutôt que de perdre l'offre.
    store = FakeOfferStore()
    client = MockLLMClient([NO_SKILLS_RESPONSE, "pas du json"])
    fetch = _fetcher()
    result = intake_offer_enriched(
        "snippet", source="adzuna", url="http://x/offre", client=client, store=store,
        fetch=fetch, extract=lambda h: "texte complet",
    )
    assert result.offer.skills == []
    assert result.offer.raw_text == "snippet"  # on n'a pas adopté le texte enrichi
    assert result.enrichment_attempted is True
    assert result.enrichment_recovered is False
    assert store.get(result.offer.id) is result.offer
    assert len(client.calls) == 2  # la 2ᵉ passe a bien été tentée


def test_enriched_falls_back_when_extract_unavailable():
    # Extra ``scrape`` absent : extract_offer_text lève RuntimeError. L'enrichissement étant
    # un bonus, on retombe sur le snippet — la passe ne doit pas tomber ni perdre l'offre.
    store = FakeOfferStore()
    client = MockLLMClient([NO_SKILLS_RESPONSE])
    fetch = _fetcher()

    def extract(html):
        raise RuntimeError("Extraction HTML indisponible : installez l'extra 'scrape'")

    result = intake_offer_enriched(
        "snippet", source="adzuna", url="http://x/offre", client=client, store=store,
        fetch=fetch, extract=extract,
    )
    assert result.offer.skills == []
    assert result.offer.raw_text == "snippet"  # texte initial conservé
    assert result.enrichment_attempted is True  # tentée…
    assert result.enrichment_recovered is False  # …mais extraction indisponible
    assert store.get(result.offer.id) is result.offer
    assert len(client.calls) == 1  # pas de seconde passe
