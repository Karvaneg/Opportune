"""Tests du modèle d'analyse de CV et de sa validation stricte (OPP-136)."""

import json

import pytest

from app.profile_analysis import (
    PROFILE_ANALYSIS_SCHEMA,
    ProfileAnalysis,
    ProfileAnalysisError,
)

VALID = {
    "name": "Marie Le Carvennec",
    "location": "Paris",
    "skills": ["Python", "SQL"],
    "languages": ["Français", "Anglais"],
    "total_experience_years": 6,
}


def test_schema_covers_every_validated_field():
    props = set(PROFILE_ANALYSIS_SCHEMA["properties"])
    assert props == set(VALID)
    assert set(PROFILE_ANALYSIS_SCHEMA["required"]) == set(VALID)
    assert PROFILE_ANALYSIS_SCHEMA["properties"]["skills"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    # total_experience_years est nullable (nombre OU null)
    assert PROFILE_ANALYSIS_SCHEMA["properties"]["total_experience_years"] == {
        "type": ["number", "null"]
    }


def test_from_json_valid():
    analysis = ProfileAnalysis.from_json(json.dumps(VALID))
    assert analysis.name == "Marie Le Carvennec"
    assert analysis.skills == ["Python", "SQL"]
    assert analysis.total_experience_years == 6.0


def test_from_json_trims_and_drops_empty_list_items():
    payload = dict(VALID, name="  Marie  ", skills=["  Python  ", "  "])
    analysis = ProfileAnalysis.from_json(json.dumps(payload))
    assert analysis.name == "Marie"
    assert analysis.skills == ["Python"]


def test_years_accepts_null():
    analysis = ProfileAnalysis.from_json(json.dumps(dict(VALID, total_experience_years=None)))
    assert analysis.total_experience_years is None


def test_years_zero_is_valid_and_distinct_from_null():
    analysis = ProfileAnalysis.from_json(json.dumps(dict(VALID, total_experience_years=0)))
    assert analysis.total_experience_years == 0.0


@pytest.mark.parametrize("bad", [-1, True, "6", []])
def test_years_rejects_invalid(bad):
    with pytest.raises(ProfileAnalysisError):
        ProfileAnalysis.from_json(json.dumps(dict(VALID, total_experience_years=bad)))


def test_from_json_rejects_invalid_json():
    with pytest.raises(ProfileAnalysisError):
        ProfileAnalysis.from_json("ceci n'est pas du json")


def test_from_dict_rejects_missing_text_field():
    with pytest.raises(ProfileAnalysisError):
        ProfileAnalysis.from_dict({k: v for k, v in VALID.items() if k != "name"})


def test_from_dict_rejects_non_string_skill():
    with pytest.raises(ProfileAnalysisError):
        ProfileAnalysis.from_dict(dict(VALID, skills=["Python", 3]))


def test_schema_output_passes_validation():
    payload = {k: ("Non précisé" if k in ("name", "location") else []) for k in VALID}
    payload["total_experience_years"] = None
    assert isinstance(ProfileAnalysis.from_dict(payload), ProfileAnalysis)
