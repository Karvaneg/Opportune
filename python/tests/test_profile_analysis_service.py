"""Tests du service d'analyse de CV par LLM (OPP-136).

Aucun appel réseau : le LLM est simulé via ``MockLLMClient``.
"""

import json

import pytest

from app.llm_client import LLMError, MockLLMClient
from app.profile_analysis import PROFILE_ANALYSIS_SCHEMA, ProfileAnalysis, ProfileAnalysisError
from app.profile_analysis_service import analyze_cv, build_profile_prompt

VALID_RESPONSE = json.dumps(
    {
        "name": "Marie",
        "location": "Paris",
        "skills": ["Python", "SQL"],
        "languages": ["Français"],
        "total_experience_years": 6,
    }
)


# --- Prompt ------------------------------------------------------------------


def test_prompt_is_deterministic_and_contains_cv():
    a = build_profile_prompt("Mon CV")
    b = build_profile_prompt("Mon CV")
    assert a == b
    assert "Mon CV" in a
    assert "name" in a and "total_experience_years" in a


def test_prompt_requires_atomic_skills_and_forbids_inventing_preferences():
    prompt = build_profile_prompt("CV")
    assert "ATOMIQUES" in prompt
    assert "N'invente aucune préférence" in prompt


def test_prompt_rejects_empty():
    with pytest.raises(ValueError):
        build_profile_prompt("   ")


# --- analyze_cv --------------------------------------------------------------


def test_analyze_cv_returns_structured_result():
    client = MockLLMClient([VALID_RESPONSE])
    analysis = analyze_cv("Texte du CV", client)
    assert isinstance(analysis, ProfileAnalysis)
    assert analysis.name == "Marie"
    assert "Texte du CV" in client.calls[0]["prompt"]


def test_analyze_cv_constrains_decoding_with_schema():
    client = MockLLMClient([VALID_RESPONSE])
    analyze_cv("Texte du CV", client)
    assert client.calls[0]["fmt"] is PROFILE_ANALYSIS_SCHEMA


def test_analyze_cv_rejects_invalid_json():
    client = MockLLMClient(["pas du json"])
    with pytest.raises(ProfileAnalysisError):
        analyze_cv("CV", client)


def test_analyze_cv_propagates_llm_error():
    client = MockLLMClient(error=LLMError("réseau"))
    with pytest.raises(LLMError):
        analyze_cv("CV", client)


def test_analyze_cv_rejects_empty_cv():
    client = MockLLMClient([VALID_RESPONSE])
    with pytest.raises(ValueError):
        analyze_cv("   ", client)
