"""Tests de la correction humaine d'un profil extrait (OPP-138).

Fausse persistance en mémoire : ni réseau, ni SQLite, ni LLM.
"""

import pytest

from app.candidate_profile import CandidateProfile, ProfileValidationError, create_profile
from app.profile_correction_service import UnknownProfileError, correct_profile


class FakeProfileStore:
    """Fausse persistance en mémoire respectant le contrat ``ProfileRepository``."""

    def __init__(self):
        self.profiles: dict[str, CandidateProfile] = {}

    def save(self, profile: CandidateProfile) -> None:
        self.profiles[profile.id] = profile

    def get(self, profile_id: str):
        return self.profiles.get(profile_id)


def _stored(**overrides) -> FakeProfileStore:
    store = FakeProfileStore()
    data = dict(
        id="cand-marie",
        name="Marie",
        skills=["Python", "SQL"],
        contract_type="CDI",
        total_experience_years=10,  # fait extrait erroné (cf. OPP-137)
        location="Paris",
    )
    data.update(overrides)
    store.save(create_profile(**data))
    return store


def test_correct_updates_field_and_locks_it():
    store = _stored()
    corrected = correct_profile("cand-marie", store=store, total_experience_years=2)
    assert corrected.total_experience_years == 2.0
    assert corrected.locked_fields == ["total_experience_years"]  # fait verrouillé
    assert store.get("cand-marie") == corrected  # persisté


def test_correct_accumulates_locks_without_duplicates():
    store = _stored()
    correct_profile("cand-marie", store=store, total_experience_years=2)
    corrected = correct_profile("cand-marie", store=store, location="Bordeaux")
    assert corrected.location == "Bordeaux"
    assert corrected.locked_fields == ["total_experience_years", "location"]

    # Re-corriger un champ déjà verrouillé ne duplique pas le verrou.
    again = correct_profile("cand-marie", store=store, total_experience_years=3)
    assert again.locked_fields == ["total_experience_years", "location"]


def test_correct_rejects_preference():
    # Seuls les faits sont corrigeables : une préférence est refusée (API honnête —
    # elle serait de toute façon réécrite par l'appelant au prochain ré-intake).
    store = _stored()
    with pytest.raises(ProfileValidationError):
        correct_profile("cand-marie", store=store, contract_type="freelance")
    assert store.get("cand-marie").contract_type == "CDI"  # inchangé


def test_correct_rejects_unknown_field():
    # Faute de frappe : « experience_years » au lieu de « total_experience_years ».
    # La correction ne doit pas être silencieusement jetée par create_profile.
    store = _stored()
    with pytest.raises(ProfileValidationError):
        correct_profile("cand-marie", store=store, experience_years=2)
    assert store.get("cand-marie").total_experience_years == 10.0  # inchangé


def test_correct_revalidates_changes():
    store = _stored()
    with pytest.raises(ProfileValidationError):
        correct_profile("cand-marie", store=store, total_experience_years=-1)
    # Rien n'a changé en base.
    assert store.get("cand-marie").total_experience_years == 10.0


def test_correct_ignores_id_and_locked_fields_in_changes():
    store = _stored()
    corrected = correct_profile(
        "cand-marie", store=store, id="autre", locked_fields=["skills"], location="Lyon"
    )
    assert corrected.id == "cand-marie"  # identité stable
    assert corrected.locked_fields == ["location"]  # verrou dérivé, pas fourni


def test_correct_requires_a_change():
    store = _stored()
    with pytest.raises(ProfileValidationError):
        correct_profile("cand-marie", store=store)


def test_correct_unknown_profile_raises():
    store = _stored()
    with pytest.raises(UnknownProfileError):
        correct_profile("inconnu", store=store, location="Lyon")
