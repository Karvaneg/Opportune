"""Tests du matching profil ↔ offre (OPP-038).

Comparaison déterministe, sans LLM ni réseau : on construit des `Offer` et
`CandidateProfile` en mémoire.
"""

from app.candidate_profile import create_profile
from app.offer import Offer
from app.offer_profile_match import (
    compare_contract_type,
    compare_location,
    compare_seniority,
    compare_skills,
    match_offer_to_profile,
)


def _offer(**overrides) -> Offer:
    data = dict(
        id="o-1",
        title="Développeur Python",
        company="Acme",
        location="Paris",
        skills=["Python", "SQL"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend.",
        attention_points=[],
        source="indeed",
        url="http://x",
        raw_text="texte",
    )
    data.update(overrides)
    return Offer(**data)


def _profile(**overrides):
    data = dict(name="Marie", skills=["Python"], contract_type="CDI")
    data.update(overrides)
    return create_profile(**data)


# --- Compétences -------------------------------------------------------------


def test_skills_matched_and_missing_case_insensitive():
    offer = _offer(skills=["Python", "SQL", "Go"])
    profile = _profile(skills=["python", "sql"])
    result = compare_skills(offer, profile)
    assert result.matched == ["Python", "SQL"]  # libellés de l'offre conservés
    assert result.missing == ["Go"]


# --- Type de contrat ---------------------------------------------------------


def test_contract_compatible_cdi():
    assert compare_contract_type(_offer(contract_type="CDI"), _profile(contract_type="CDI")).compatible is True


def test_contract_incompatible():
    result = compare_contract_type(_offer(contract_type="Freelance"), _profile(contract_type="CDI"))
    assert result.compatible is False


def test_contract_les_deux_accepts_freelance():
    result = compare_contract_type(_offer(contract_type="Freelance"), _profile(contract_type="les deux"))
    assert result.compatible is True


# --- Localisation ------------------------------------------------------------


def test_location_match_substring():
    result = compare_location(_offer(location="Paris"), _profile(location="Paris 15e"))
    assert result.status == "match"


def test_location_mismatch():
    result = compare_location(_offer(location="Lyon"), _profile(location="Paris"))
    assert result.status == "mismatch"


def test_location_not_blocking_when_profile_mobile():
    result = compare_location(
        _offer(location="Lyon"), _profile(location="Paris", mobility="France entière")
    )
    assert result.status == "not_blocking"
    assert result.reason == "profile-mobility"


def test_location_unknown_when_profile_missing():
    result = compare_location(_offer(location="Lyon"), _profile())  # profil sans location
    assert result.status == "unknown"


# --- Séniorité / expérience --------------------------------------------------


def test_seniority_ok_when_enough_experience():
    result = compare_seniority(_offer(seniority="Senior"), _profile(total_experience_years=6))
    assert result.required_years == 5
    assert result.status == "ok"


def test_seniority_insufficient():
    result = compare_seniority(_offer(seniority="Senior"), _profile(total_experience_years=2))
    assert result.status == "insufficient"


def test_seniority_unknown_when_profile_missing_years():
    result = compare_seniority(_offer(seniority="Senior"), _profile())
    assert result.status == "unknown"


def test_seniority_unknown_when_label_unrecognized():
    result = compare_seniority(_offer(seniority="Ninja"), _profile(total_experience_years=6))
    assert result.status == "unknown"


def test_seniority_not_required_when_unspecified():
    result = compare_seniority(_offer(seniority="Non précisé"), _profile(total_experience_years=6))
    assert result.status == "not_required"


# --- Point d'entrée ----------------------------------------------------------


def test_match_offer_to_profile_aggregates_all_dimensions():
    result = match_offer_to_profile(
        _offer(), _profile(skills=["Python"], total_experience_years=6, location="Paris")
    )
    assert result.skills.matched == ["Python"]
    assert result.skills.missing == ["SQL"]
    assert result.contract_type.compatible is True
    assert result.location.status == "match"
    assert result.seniority.status == "ok"
