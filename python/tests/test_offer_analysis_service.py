"""Tests du service d'analyse d'offre par LLM (OPP-036).

Aucun appel réseau : le LLM est simulé via ``MockLLMClient``.
"""

import json

import pytest

from app.llm_client import LLMError, MockLLMClient
from app.offer_analysis import OFFER_ANALYSIS_SCHEMA, OfferAnalysis, OfferAnalysisError
from app.offer_analysis_service import analyze_offer, build_analysis_prompt

VALID_RESPONSE = json.dumps(
    {
        "title": "Développeur Python",
        "company": "Acme",
        "location": "Paris",
        "seniority": "Senior",
        "contract_type": "CDI",
        "summary": "Backend data.",
        "skills": ["Python"],
        "attention_points": [],
    }
)


# --- Prompt ------------------------------------------------------------------


def test_prompt_is_deterministic_and_contains_offer():
    a = build_analysis_prompt("Offre XYZ")
    b = build_analysis_prompt("Offre XYZ")
    assert a == b  # déterministe
    assert "Offre XYZ" in a
    assert "title" in a and "attention_points" in a  # clés attendues annoncées


def test_prompt_requires_atomic_skills():
    # Le prompt doit exiger des compétences atomiques : c'est ce qui évite les blocs
    # composés qui cassent le match exact de compare_skills (une techno par élément).
    prompt = build_analysis_prompt("Offre XYZ")
    assert "ATOMIQUES" in prompt
    assert "Back-end (PostgreSQL, Express)" in prompt  # contre-exemple explicite


def test_prompt_excludes_non_skills():
    # OPP-142 : la consigne cadre skills = technos concrètes et exclut explicitement
    # normes, organismes et tâches (contre-exemple de tâche présent, style OPP-135).
    prompt = build_analysis_prompt("Offre XYZ")
    assert "CONCRÈTES" in prompt
    assert "Optimisation de calculs" in prompt  # contre-exemple de tâche


def test_prompt_forbids_inventing_skills():
    # OPP-213 : la consigne interdit explicitement d'inventer des compétences absentes
    # de l'offre (cause principale du delta observé entre offre réelle et stack extraite).
    prompt = build_analysis_prompt("Offre XYZ")
    assert "N'INVENTE RIEN" in prompt
    assert "liste skills VIDE" in prompt  # mieux vaut vide que supposé


def test_prompt_trims_and_rejects_empty():
    assert build_analysis_prompt("  Offre  ").endswith("Offre")
    with pytest.raises(ValueError):
        build_analysis_prompt("   ")


# --- analyze_offer -----------------------------------------------------------


def test_analyze_offer_returns_structured_result():
    client = MockLLMClient([VALID_RESPONSE])
    analysis = analyze_offer("Texte de l'offre", client)

    assert isinstance(analysis, OfferAnalysis)
    assert analysis.title == "Développeur Python"
    # Le prompt réellement envoyé au LLM porte le texte de l'offre.
    assert "Texte de l'offre" in client.calls[0]["prompt"]


def test_analyze_offer_constrains_decoding_with_schema():
    # Le service contraint le décodage au schéma d'OfferAnalysis (structured outputs) :
    # c'est ce qui empêche le petit modèle local d'émettre du JSON malformé.
    client = MockLLMClient([VALID_RESPONSE])
    analyze_offer("Texte de l'offre", client)
    assert client.calls[0]["fmt"] is OFFER_ANALYSIS_SCHEMA


def test_analyze_offer_uses_zero_temperature():
    # OPP-213 : l'intake fixe la température à 0 pour une extraction déterministe, sans
    # laisser le défaut serveur (~0.8) pousser le modèle à inventer une stack.
    client = MockLLMClient([VALID_RESPONSE])
    analyze_offer("Texte de l'offre", client)
    assert client.calls[0]["temperature"] == 0.0


def test_analyze_offer_rejects_invalid_json():
    client = MockLLMClient(["ceci n'est pas du json"])
    with pytest.raises(OfferAnalysisError):
        analyze_offer("Texte", client)


def test_analyze_offer_rejects_incomplete_response():
    incomplete = json.dumps({"title": "Dev"})  # champs manquants
    client = MockLLMClient([incomplete])
    with pytest.raises(OfferAnalysisError):
        analyze_offer("Texte", client)


def test_analyze_offer_propagates_llm_error():
    client = MockLLMClient(error=LLMError("réseau"))
    with pytest.raises(LLMError):
        analyze_offer("Texte", client)


def test_analyze_offer_rejects_empty_offer():
    client = MockLLMClient([VALID_RESPONSE])
    with pytest.raises(ValueError):
        analyze_offer("   ", client)
