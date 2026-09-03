"""Tests de la persistance SQLite des profils candidats (OPP-017).

Base SQLite en mémoire (``:memory:``) : aucune I/O disque, aucun réseau.
"""

import pytest

from app.candidate_profile import CandidateProfile, create_profile
from app.db import connect
from app.profile_store import ProfileRepository, ProfileStore


def _profile(**overrides) -> CandidateProfile:
    data = dict(
        id="p-1",
        name="Marie",
        skills=["Python", "SQL"],
        contract_type="les deux",
        total_experience_years=6,
        location="Paris",
        target_salary=55000,
        target_daily_rate=600,
        languages=["FR", "EN"],
        availability="sous 1 mois",
        constraints=["pas de grands déplacements"],
    )
    data.update(overrides)
    return create_profile(**data)


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield ProfileStore(conn)
    conn.close()


def test_store_satisfies_repository_protocol(store):
    assert isinstance(store, ProfileRepository)


def test_save_then_get_roundtrip(store):
    profile = _profile()
    store.save(profile)
    assert store.get("p-1") == profile  # listes JSON restaurées, égalité dataclass


def test_get_unknown_returns_none(store):
    assert store.get("nope") is None


def test_optional_fields_persist_as_null(store):
    profile = create_profile(id="p-2", name="A", skills=["X"], contract_type="CDI")
    store.save(profile)
    fetched = store.get("p-2")
    assert fetched.total_experience_years is None
    assert fetched.location is None
    assert fetched.target_daily_rate is None


def test_save_is_an_upsert_not_a_duplicate(store):
    store.save(_profile(name="v1"))
    store.save(_profile(name="v2"))  # même id
    assert store.count() == 1
    assert store.get("p-1").name == "v2"
