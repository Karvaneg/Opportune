"""Tests du pipeline d'analyse de bout en bout (OPP-0392).

Faux LLM (`MockLLMClient`) + persistance SQLite en mémoire : aucun réseau.
"""

import json
from dataclasses import replace

import pytest

from app.analysis_pipeline import (
    DecisionDossier,
    OfferInput,
    run_pipeline,
    run_pipeline_batch,
)
from app.candidate_profile import create_profile
from app.db import connect
from app.llm_client import MockLLMClient
from app.offer_analysis import OfferAnalysisError
from app.offer_store import OfferStore


def _analysis(**overrides) -> str:
    data = {
        "title": "Développeur Python Senior",
        "company": "Acme",
        "location": "Paris",
        "seniority": "Senior",
        "contract_type": "CDI",
        "summary": "Backend data.",
        "skills": ["Python", "SQL"],
        "attention_points": [],
    }
    data.update(overrides)
    return json.dumps(data)


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield OfferStore(conn)
    conn.close()


def _strong_profile():
    return create_profile(
        name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    )


def test_pipeline_produces_full_dossier_and_persists(store):
    client = MockLLMClient([_analysis()])
    dossier = run_pipeline(
        "texte offre", source="indeed", url="http://x",
        profile=_strong_profile(), client=client, store=store,
    )
    assert isinstance(dossier, DecisionDossier)
    assert dossier.offer.title == "Développeur Python Senior"
    assert dossier.explanation.score == 100
    assert dossier.recommendation.action == "postuler"
    # l'offre a bien été persistée (le store attribue la date d'ingestion, OPP-152 ;
    # le reste est identique au dossier).
    stored = store.get(dossier.offer.id)
    assert replace(stored, created_at="") == dossier.offer
    assert stored.created_at != ""


def test_pipeline_weak_match_recommends_ignorer(store):
    client = MockLLMClient([_analysis()])
    weak = create_profile(
        name="Bob", skills=["Java"], contract_type="freelance",
        location="Lyon", total_experience_years=1,
    )
    dossier = run_pipeline("texte", source="indeed", profile=weak, client=client, store=store)
    assert dossier.explanation.score == 0
    assert dossier.recommendation.action == "ignorer"


def test_pipeline_invalid_analysis_persists_nothing(store):
    client = MockLLMClient(["pas du json"])
    with pytest.raises(OfferAnalysisError):
        run_pipeline("texte", source="indeed", profile=_strong_profile(), client=client, store=store)
    assert store.count() == 0


def test_pipeline_custom_thresholds_shift_recommendation(store):
    # skills 1/2 → score 78 ; avec high=80 la reco bascule de postuler à a_etudier.
    client = MockLLMClient([_analysis(skills=["Python", "Rust"])])
    dossier = run_pipeline(
        "texte", source="indeed", profile=_strong_profile(), client=client, store=store,
        high=80, medium=50,
    )
    assert dossier.explanation.score == 78
    assert dossier.recommendation.action == "a_etudier"


def test_pipeline_invalid_thresholds_persist_nothing(store):
    # Seuils incohérents : le pipeline doit échouer AVANT toute persistance.
    client = MockLLMClient([_analysis()])
    with pytest.raises(ValueError):
        run_pipeline(
            "texte", source="indeed", profile=_strong_profile(), client=client, store=store,
            high=40, medium=80,
        )
    assert store.count() == 0


def test_pipeline_batch_preserves_order_and_persists_all(store):
    client = MockLLMClient([
        _analysis(title="Offre A"),
        _analysis(title="Offre B"),
    ])
    inputs = [
        OfferInput(raw_text="t1", source="indeed", url="http://a"),
        OfferInput(raw_text="t2", source="indeed", url="http://b"),
    ]
    dossiers = run_pipeline_batch(inputs, profile=_strong_profile(), client=client, store=store)
    assert [d.offer.title for d in dossiers] == ["Offre A", "Offre B"]
    assert store.count() == 2
