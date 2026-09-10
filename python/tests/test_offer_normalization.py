"""Tests de la normalisation déterministe des champs d'offre (OPP-037)."""

from app.offer_normalization import (
    normalize_contract,
    normalize_location,
    normalize_skills,
)


def test_contract_canonicalises_known_synonyms():
    assert normalize_contract("CDI") == "CDI"
    assert normalize_contract("  cdi ") == "CDI"
    assert normalize_contract("Indépendant") == "Freelance"
    assert normalize_contract("mission") == "Freelance"
    assert normalize_contract("Apprentissage") == "Alternance"


def test_contract_keeps_unknown_value_cleaned():
    assert normalize_contract("  Portage   salarial ") == "Portage salarial"


def test_location_collapses_whitespace():
    assert normalize_location("  Paris   15e  ") == "Paris 15e"


def test_skills_dedupe_case_insensitive_keep_order():
    assert normalize_skills(["Python", "python", "SQL", "  Python  "]) == ["Python", "SQL"]


def test_skills_drop_empty_entries():
    assert normalize_skills(["  ", "Docker", ""]) == ["Docker"]


def test_skills_atomize_parenthesised_enumeration():
    # « Back-end (PostgreSQL, Express) » doit être éclaté en éléments atomiques.
    assert normalize_skills(["Back-end (PostgreSQL, Express)"]) == [
        "Back-end",
        "PostgreSQL",
        "Express",
    ]


def test_skills_atomize_slash_group():
    assert normalize_skills(["HTML/CSS/JS"]) == ["HTML", "CSS", "JS"]


def test_skills_keep_atomic_slash_acronyms_whole():
    # CI/CD, TCP/IP… sont atomiques : ne pas les éclater sur le « / ».
    assert normalize_skills(["CI/CD", "TCP/IP"]) == ["CI/CD", "TCP/IP"]


def test_skills_atomize_then_dedupe_across_entries():
    # Éclatement puis dédoublonnage casse-insensible entre entrées distinctes.
    assert normalize_skills(["React, Node", "node", "React"]) == ["React", "Node"]
