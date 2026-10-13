"""Tests des briques communes aux runners de collecte (OPP-120).

``run_collection`` et ``format_report`` sont indépendants de la source : on les vérifie avec
une source factice, un faux LLM et une base en mémoire — sans réseau ni Ollama.
"""

import json

from app.collection_runner import format_report, run_collection
from app.db import connect
from app.llm_client import MockLLMClient
from app.offer import compute_offer_id
from app.offer_collection import CollectionFailure, CollectionReport
from app.offer_source import RawOffer
from app.offer_store import OfferStore


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


def test_run_collection_persists_offers_into_real_store():
    store = OfferStore(connect(":memory:"))
    source = ListSource(
        [
            RawOffer(source="src", raw_text="offre A", url="https://x/a"),
            RawOffer(source="src", raw_text="offre B", url="https://x/b"),
        ]
    )

    report = run_collection(
        source, llm_client=MockLLMClient([_analysis(), _analysis()]), store=store
    )

    assert report.stored == 2
    assert store.get(compute_offer_id("src", "https://x/a", "offre A")) is not None


def test_format_report_includes_counts_and_failures():
    report = CollectionReport(
        collected=3,
        stored=1,
        duplicates=1,
        failures=(
            CollectionFailure(
                raw=RawOffer(source="src", raw_text="x", url="https://x/ko"), error="LLM KO"
            ),
        ),
        source_error=None,
    )
    text = format_report(report)
    assert "Collectées : 3" in text
    assert "Persistées : 1" in text
    assert "Doublons   : 1" in text
    assert "Échecs     : 1" in text
    assert "https://x/ko" in text and "LLM KO" in text


def test_format_report_surfaces_source_error():
    report = CollectionReport(
        collected=0, stored=0, duplicates=0, failures=(), source_error="HTTP 429"
    )
    assert "Erreur source : HTTP 429" in format_report(report)
