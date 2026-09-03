"""Tests de l'intégration de l'analyse LLM dans le cycle d'une offre (OPP-037).

Faux LLM (``MockLLMClient``) + fausse persistance (``FakeOfferStore``) : ni réseau,
ni SQLite.
"""

import json

import pytest

from app.llm_client import LLMError, MockLLMClient
from app.offer import Offer
from app.offer_analysis import OfferAnalysisError
from app.offer_intake_service import intake_offer

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
        "texte brut", source="indeed", url="http://x", client=MockLLMClient([VALID_RESPONSE]), store=store
    )
    assert offer.contract_type == "CDI"  # normalisé
    assert offer.skills == ["Python"]  # dédoublonné
    assert store.get(offer.id) == offer  # bien persistée


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
