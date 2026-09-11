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


def test_locked_fields_roundtrip(store):
    profile = _profile(locked_fields=["total_experience_years", "location"])
    store.save(profile)
    assert store.get("p-1").locked_fields == ["total_experience_years", "location"]


def test_migrates_legacy_table_without_locked_fields():
    # Une base antérieure à OPP-138 : table profiles sans la colonne locked_fields.
    conn = connect(":memory:")
    conn.execute(
        """
        CREATE TABLE profiles (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, skills TEXT NOT NULL,
            contract_type TEXT NOT NULL, structured_skills TEXT NOT NULL,
            experiences TEXT NOT NULL, total_experience_years REAL, location TEXT,
            mobility TEXT, remote TEXT, target_salary REAL, target_daily_rate REAL,
            languages TEXT NOT NULL, availability TEXT, constraints TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO profiles (id, name, skills, contract_type, structured_skills, "
        "experiences, languages, constraints) VALUES "
        "('old', 'Ancien', '[\"Python\"]', 'CDI', '[]', '[]', '[]', '[]')"
    )
    conn.commit()

    # L'ouverture via ProfileStore ajoute la colonne et lit le profil legacy sans verrou.
    store = ProfileStore(conn)
    migrated = store.get("old")
    assert migrated is not None
    assert migrated.locked_fields == []
    conn.close()
