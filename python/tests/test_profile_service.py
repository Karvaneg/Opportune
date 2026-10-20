"""Tests du service de profil candidat (consultation / édition des compétences, OPP-158).

Dépôt de profils factice (contrat ``ProfileRepository``) : ni SQLite ni réseau. On vérifie la
lecture, le remplacement normalisé + revalidé des compétences, la persistance, et les cas
limites (candidat sans profil → ``None`` ; liste vide → ``ProfileValidationError``).
"""

import pytest

from app.candidate_profile import ProfileValidationError, create_profile
from app.profile_service import ProfileService


class FakeProfileStore:
    def __init__(self, *profiles):
        self.saved = {p.id: p for p in profiles}

    def get(self, profile_id):
        return self.saved.get(profile_id)

    def save(self, profile):
        self.saved[profile.id] = profile


def _profile(candidate_id="cand-1", skills=("React",)):
    return create_profile(
        id=candidate_id, name="Marie", skills=list(skills), contract_type="CDI"
    )


def test_get_returns_profile_then_none():
    service = ProfileService(FakeProfileStore(_profile()))
    assert service.get("cand-1").id == "cand-1"
    assert service.get("absent") is None


def test_update_skills_replaces_persists_and_returns():
    store = FakeProfileStore(_profile(skills=["React"]))
    service = ProfileService(store)

    updated = service.update_skills("cand-1", ["React", "HTML5", "CSS3", "Agile"])

    assert "Agile" in updated.skills
    assert set(updated.skills) >= {"React", "HTML5", "CSS3", "Agile"}
    # Persisté : une relecture reflète la nouvelle liste.
    assert store.get("cand-1").skills == updated.skills


def test_update_skills_locks_skills_against_reintake():
    # OPP-158 : l'édition manuelle verrouille ``skills`` (OPP-138), sinon un ré-intake du CV
    # réécraserait la curation. Le verrou est cumulé avec ceux déjà posés.
    store = FakeProfileStore(_profile(skills=["React"]))
    updated = ProfileService(store).update_skills("cand-1", ["React", "HTML5", "Agile"])
    assert "skills" in updated.locked_fields
    assert store.get("cand-1").locked_fields == updated.locked_fields


def test_update_skills_normalizes_input():
    # normalize_skills atomise/épure (OPP-135) : espaces superflus et entrées vides écartés.
    store = FakeProfileStore(_profile())
    updated = ProfileService(store).update_skills("cand-1", ["  Scrum  ", ""])
    assert "Scrum" in updated.skills
    assert "" not in updated.skills


def test_update_skills_unknown_candidate_returns_none():
    service = ProfileService(FakeProfileStore(_profile()))
    assert service.update_skills("absent", ["React"]) is None


def test_update_skills_empty_list_is_rejected():
    service = ProfileService(FakeProfileStore(_profile()))
    with pytest.raises(ProfileValidationError):
        service.update_skills("cand-1", [])


def test_update_skills_only_blanks_is_rejected():
    # Après normalisation il ne reste aucune compétence → profil non exploitable.
    service = ProfileService(FakeProfileStore(_profile()))
    with pytest.raises(ProfileValidationError):
        service.update_skills("cand-1", ["   ", ""])
