"""Tests du modèle de profil candidat et de sa validation (OPP-017)."""

import pytest

from app.candidate_profile import (
    CandidateProfile,
    ProfileValidationError,
    create_profile,
    update_profile,
)


def test_create_minimal_profile_with_defaults():
    profile = create_profile(name="Marie", skills=["Python"], contract_type="CDI")
    assert isinstance(profile, CandidateProfile)
    assert profile.name == "Marie"
    assert profile.skills == ["Python"]
    assert profile.contract_type == "CDI"
    # défauts neutres
    assert profile.languages == []
    assert profile.total_experience_years is None
    assert profile.id  # id généré


def test_create_generates_unique_ids():
    a = create_profile(name="A", skills=["X"], contract_type="CDI")
    b = create_profile(name="B", skills=["Y"], contract_type="CDI")
    assert a.id != b.id


def test_explicit_id_is_kept():
    profile = create_profile(id="p-1", name="A", skills=["X"], contract_type="freelance")
    assert profile.id == "p-1"


def test_skills_are_cleaned_of_blanks():
    profile = create_profile(
        name="A", skills=["  Python  ", "", "  "], contract_type="les deux"
    )
    assert profile.skills == ["Python"]


def test_name_is_required():
    with pytest.raises(ProfileValidationError):
        create_profile(name="  ", skills=["X"], contract_type="CDI")


def test_skills_required_non_empty():
    with pytest.raises(ProfileValidationError):
        create_profile(name="A", skills=[], contract_type="CDI")


def test_contract_type_must_be_known():
    with pytest.raises(ProfileValidationError):
        create_profile(name="A", skills=["X"], contract_type="stage")


def test_availability_option_accepted():
    profile = create_profile(
        name="A", skills=["X"], contract_type="CDI", availability="sous 1 mois"
    )
    assert profile.availability == "sous 1 mois"


def test_availability_iso_date_accepted():
    profile = create_profile(
        name="A", skills=["X"], contract_type="CDI", availability="2026-10-01"
    )
    assert profile.availability == "2026-10-01"


def test_availability_invalid_rejected():
    with pytest.raises(ProfileValidationError):
        create_profile(name="A", skills=["X"], contract_type="CDI", availability="bientôt")


@pytest.mark.parametrize("value", ["20261001", "2026-W40-3"])
def test_availability_non_canonical_iso_rejected(value):
    # date.fromisoformat (3.11+) accepte ces formes ; le contrat exige YYYY-MM-DD.
    with pytest.raises(ProfileValidationError):
        create_profile(name="A", skills=["X"], contract_type="CDI", availability=value)


def test_structured_skills_must_be_objects():
    with pytest.raises(ProfileValidationError):
        create_profile(
            name="A", skills=["X"], contract_type="CDI", structured_skills=["Python"]
        )


def test_experiences_must_be_objects():
    with pytest.raises(ProfileValidationError):
        create_profile(
            name="A", skills=["X"], contract_type="CDI", experiences=["dev chez X"]
        )


def test_negative_numeric_rejected():
    with pytest.raises(ProfileValidationError):
        create_profile(
            name="A", skills=["X"], contract_type="CDI", target_salary=-1
        )


def test_cdi_and_freelance_rates_are_distinct_fields():
    profile = create_profile(
        name="A",
        skills=["X"],
        contract_type="les deux",
        target_salary=55000,
        target_daily_rate=600,
    )
    assert profile.target_salary == 55000.0
    assert profile.target_daily_rate == 600.0


def test_update_profile_keeps_id_and_is_immutable():
    profile = create_profile(id="p-1", name="A", skills=["X"], contract_type="CDI")
    updated = update_profile(profile, name="B", id="hacked")
    assert updated.id == "p-1"  # id stable, changement d'id ignoré
    assert updated.name == "B"
    assert profile.name == "A"  # original inchangé


def test_update_profile_revalidates_changes():
    profile = create_profile(id="p-1", name="A", skills=["X"], contract_type="CDI")
    with pytest.raises(ProfileValidationError):
        update_profile(profile, contract_type="stage")
    with pytest.raises(ProfileValidationError):
        update_profile(profile, skills=[])
    with pytest.raises(ProfileValidationError):
        update_profile(profile, target_salary=-1)
