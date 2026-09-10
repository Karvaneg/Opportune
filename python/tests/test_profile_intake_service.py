"""Tests de l'intake de profil depuis un CV (OPP-136).

Faux LLM (``MockLLMClient``) + fausse persistance : ni réseau, ni SQLite, ni PDF.
"""

import json

import pytest

from app.candidate_profile import CandidateProfile, ProfileValidationError
from app.llm_client import LLMError, MockLLMClient
from app.profile_analysis import ProfileAnalysisError
from app.profile_intake_service import intake_profile

VALID_RESPONSE = json.dumps(
    {
        "name": "Marie",
        "location": "Paris",
        # Bloc composé volontaire : la normalisation (OPP-135) doit l'éclater.
        "skills": ["Back-end (Python, SQL)", "React"],
        "languages": ["Français"],
        "total_experience_years": 6,
    }
)


class FakeProfileStore:
    """Fausse persistance en mémoire respectant le contrat ``ProfileRepository``."""

    def __init__(self):
        self.profiles: dict[str, CandidateProfile] = {}

    def save(self, profile: CandidateProfile) -> None:
        self.profiles[profile.id] = profile

    def get(self, profile_id: str):
        return self.profiles.get(profile_id)


def test_intake_analyzes_merges_and_persists():
    store = FakeProfileStore()
    profile = intake_profile(
        "texte du CV",
        contract_type="CDI",
        client=MockLLMClient([VALID_RESPONSE]),
        store=store,
        id="cand-marie",
    )
    assert profile.name == "Marie"
    assert profile.contract_type == "CDI"  # préférence saisie
    assert profile.location == "Paris"  # fait extrait
    assert profile.total_experience_years == 6.0
    # skills atomisés (OPP-135) : le bloc « Back-end (Python, SQL) » est éclaté
    assert profile.skills == ["Back-end", "Python", "SQL", "React"]
    assert store.get("cand-marie") == profile


def test_intake_carries_supplied_preferences():
    store = FakeProfileStore()
    profile = intake_profile(
        "CV",
        contract_type="freelance",
        client=MockLLMClient([VALID_RESPONSE]),
        store=store,
        target_daily_rate=500,
        mobility="France entière",
    )
    assert profile.contract_type == "freelance"
    assert profile.target_daily_rate == 500.0
    assert profile.mobility == "France entière"


def test_intake_upserts_on_explicit_id():
    store = FakeProfileStore()
    client = MockLLMClient([VALID_RESPONSE, VALID_RESPONSE])
    first = intake_profile("CV", contract_type="CDI", client=client, store=store, id="cand-marie")
    second = intake_profile("CV", contract_type="CDI", client=client, store=store, id="cand-marie")
    assert first.id == second.id == "cand-marie"
    assert len(store.profiles) == 1  # remplace le profil, pas de doublon


def test_intake_requires_valid_contract_type():
    store = FakeProfileStore()
    with pytest.raises(ProfileValidationError):
        intake_profile(
            "CV", contract_type="temps partiel", client=MockLLMClient([VALID_RESPONSE]), store=store
        )
    assert store.profiles == {}  # rien persisté si la préférence est invalide


def test_intake_rejects_preference_colliding_with_cv_fact():
    store = FakeProfileStore()
    with pytest.raises(ProfileValidationError):
        intake_profile(
            "CV",
            contract_type="CDI",
            client=MockLLMClient([VALID_RESPONSE]),
            store=store,
            location="Lyon",  # collision : location est un fait du CV
        )
    assert store.profiles == {}


def test_intake_rejects_cv_without_skills():
    store = FakeProfileStore()
    response = json.dumps(
        {
            "name": "Marie",
            "location": "Paris",
            "skills": [],  # analyse valide mais aucune compétence
            "languages": ["Français"],
            "total_experience_years": 6,
        }
    )
    with pytest.raises(ProfileValidationError):
        intake_profile("CV", contract_type="CDI", client=MockLLMClient([response]), store=store)
    assert store.profiles == {}


def test_intake_rejects_invalid_analysis_and_persists_nothing():
    store = FakeProfileStore()
    with pytest.raises(ProfileAnalysisError):
        intake_profile("CV", contract_type="CDI", client=MockLLMClient(["pas du json"]), store=store)
    assert store.profiles == {}


def test_intake_propagates_llm_error():
    store = FakeProfileStore()
    with pytest.raises(LLMError):
        intake_profile(
            "CV", contract_type="CDI", client=MockLLMClient(error=LLMError("réseau")), store=store
        )
    assert store.profiles == {}
