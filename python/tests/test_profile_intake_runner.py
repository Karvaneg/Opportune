"""Tests du cœur pur du runner d'intake de profil (OPP-137).

On teste ``resolve_intake_preferences`` (parsing/validation d'environnement) sans IO :
``main`` (PDF + Ollama + SQLite) n'est pas testé (pragma).
"""

import pytest

from hermes.profile_intake import resolve_intake_preferences


def test_contract_type_required_and_validated():
    contract_type, candidate_id, prefs = resolve_intake_preferences(
        {"OPPORTUNE_CONTRACT_TYPE": "CDI"}
    )
    assert contract_type == "CDI"
    assert candidate_id is None
    assert prefs == {}


@pytest.mark.parametrize("env", [{}, {"OPPORTUNE_CONTRACT_TYPE": "temps partiel"}, {"OPPORTUNE_CONTRACT_TYPE": ""}])
def test_invalid_or_missing_contract_type_raises(env):
    with pytest.raises(ValueError):
        resolve_intake_preferences(env)


def test_reads_candidate_id():
    _, candidate_id, _ = resolve_intake_preferences(
        {"OPPORTUNE_CONTRACT_TYPE": "freelance", "OPPORTUNE_CANDIDATE_ID": "cand-marie"}
    )
    assert candidate_id == "cand-marie"


def test_parses_optional_preferences():
    _, _, prefs = resolve_intake_preferences(
        {
            "OPPORTUNE_CONTRACT_TYPE": "les deux",
            "OPPORTUNE_TARGET_SALARY": "48000",
            "OPPORTUNE_MOBILITY": "  France entière  ",
            "OPPORTUNE_REMOTE": "",  # vide → ignoré
        }
    )
    assert prefs == {"target_salary": 48000.0, "mobility": "France entière"}


def test_malformed_number_preference_raises():
    with pytest.raises(ValueError):
        resolve_intake_preferences(
            {"OPPORTUNE_CONTRACT_TYPE": "CDI", "OPPORTUNE_TARGET_SALARY": "beaucoup"}
        )
