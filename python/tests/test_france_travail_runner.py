"""Tests du runner de collecte France Travail (OPP-120).

Collaborateurs injectés : source factice, faux LLM, base en mémoire — aucune dépendance
réseau ni Ollama. On vérifie l'assemblage de la passe, le mapping des options CLI vers les
filtres de recherche, la synthèse du bilan et le code de sortie sur erreur de source.
"""

import json

from app.db import connect
from app.france_travail_runner import (
    _filters_from_args,
    _format_report,
    run_france_travail_collection,
)
from app.france_travail_source import FranceTravailSource
from app.llm_client import MockLLMClient
from app.offer import compute_offer_id
from app.offer_collection import CollectionFailure, CollectionReport
from app.offer_source import RawOffer
from app.offer_store import OfferStore


class _Args:
    def __init__(self, mots_cles="", code_rome="", commune=""):
        self.mots_cles = mots_cles
        self.code_rome = code_rome
        self.commune = commune


class ListSource:
    def __init__(self, raws):
        self._raws = list(raws)

    def fetch(self):
        return list(self._raws)


def _analysis():
    return json.dumps(
        {
            "title": "Dév",
            "company": "Acme",
            "location": "Paris",
            "seniority": "Senior",
            "contract_type": "cdi",
            "summary": "Backend.",
            "skills": ["Python"],
            "attention_points": [],
        }
    )


def test_filters_from_args_keeps_only_non_empty():
    args = _Args(mots_cles="python", code_rome="", commune="75056")
    assert _filters_from_args(args) == {"motsCles": "python", "commune": "75056"}


def test_filters_from_args_empty_when_no_option():
    assert _filters_from_args(_Args()) == {}


def test_run_collection_persists_offers_into_real_store():
    store = OfferStore(connect(":memory:"))
    source = ListSource(
        [
            RawOffer(source="france-travail", raw_text="offre A", url="https://x/a"),
            RawOffer(source="france-travail", raw_text="offre B", url="https://x/b"),
        ]
    )

    report = run_france_travail_collection(
        source=source, llm_client=MockLLMClient([_analysis(), _analysis()]), store=store
    )

    assert report.stored == 2
    assert store.get(compute_offer_id("france-travail", "https://x/a", "offre A")) is not None


def test_format_report_includes_counts_and_failures():
    report = CollectionReport(
        collected=3,
        stored=1,
        duplicates=1,
        failures=(
            CollectionFailure(
                raw=RawOffer(source="ft", raw_text="x", url="https://x/ko"), error="LLM KO"
            ),
        ),
        source_error=None,
    )
    text = _format_report(report)
    assert "Collectées : 3" in text
    assert "Persistées : 1" in text
    assert "Doublons   : 1" in text
    assert "Échecs     : 1" in text
    assert "https://x/ko" in text and "LLM KO" in text


def test_format_report_surfaces_source_error():
    report = CollectionReport(collected=0, stored=0, duplicates=0, failures=(), source_error="HTTP 429")
    assert "Erreur source : HTTP 429" in _format_report(report)


def test_france_travail_source_is_a_valid_source_protocol():
    # Garde-fou : le type réel satisfait bien le port consommé par le runner.
    from app.france_travail_client import FranceTravailClient, FranceTravailCredentials
    from app.offer_source import SourceOffres

    source = FranceTravailSource(
        FranceTravailClient(FranceTravailCredentials("c", "s"), transport=lambda *a: None)
    )
    assert isinstance(source, SourceOffres)
