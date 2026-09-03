"""Tests du modèle d'analyse d'offre et de sa validation stricte (OPP-036)."""

import json

import pytest

from app.offer_analysis import OfferAnalysis, OfferAnalysisError

VALID = {
    "title": "Développeur Python",
    "company": "Acme",
    "location": "Paris",
    "seniority": "Senior",
    "contract_type": "CDI",
    "summary": "Poste backend orienté data.",
    "skills": ["Python", "SQL"],
    "attention_points": ["Astreintes"],
}


def test_from_json_valid():
    analysis = OfferAnalysis.from_json(json.dumps(VALID))
    assert analysis.title == "Développeur Python"
    assert analysis.skills == ["Python", "SQL"]
    assert analysis.attention_points == ["Astreintes"]


def test_from_json_trims_values():
    payload = dict(VALID, title="  Dev  ", skills=["  Python  ", "  "])
    analysis = OfferAnalysis.from_json(json.dumps(payload))
    assert analysis.title == "Dev"
    assert analysis.skills == ["Python"]  # entrées vides écartées


def test_empty_lists_are_allowed():
    payload = dict(VALID, skills=[], attention_points=[])
    analysis = OfferAnalysis.from_json(json.dumps(payload))
    assert analysis.skills == []
    assert analysis.attention_points == []


def test_extra_keys_are_ignored():
    # Tolérance en lecture : une clé inattendue n'empêche pas l'analyse.
    payload = dict(VALID, salary="55k", extra={"foo": "bar"})
    analysis = OfferAnalysis.from_json(json.dumps(payload))
    assert analysis.title == "Développeur Python"
    assert not hasattr(analysis, "salary")


def test_malformed_json_is_rejected():
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_json("pas du json {")


def test_non_object_json_is_rejected():
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_json("[1, 2, 3]")


def test_missing_text_field_is_rejected():
    payload = dict(VALID)
    del payload["company"]
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_dict(payload)


def test_empty_text_field_is_rejected():
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_dict(dict(VALID, summary="   "))


def test_wrong_type_text_field_is_rejected():
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_dict(dict(VALID, title=123))


def test_missing_list_field_is_rejected():
    payload = dict(VALID)
    del payload["skills"]
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_dict(payload)


def test_list_field_with_non_string_item_is_rejected():
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_dict(dict(VALID, skills=["Python", 42]))


def test_list_field_wrong_type_is_rejected():
    with pytest.raises(OfferAnalysisError):
        OfferAnalysis.from_dict(dict(VALID, attention_points="Astreintes"))
