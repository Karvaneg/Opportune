"""Tests de la persistance SQLite des lettres (OPP-147).

Base SQLite en mémoire : aucune I/O disque, aucun réseau.
"""

import pytest

from app.db import connect
from app.letter import SOURCE_AI, SOURCE_HUMAN, Letter
from app.letter_store import LetterRepository, LetterStore

_BODY = "Corps de lettre suffisamment long pour être plausible et exploitable."


def _letter(**overrides) -> Letter:
    data = dict(
        recommendation_id="cand-1:off1",
        body=_BODY,
        source=SOURCE_AI,
        model="mock",
        created_at="t0",
        updated_at="t0",
    )
    data.update(overrides)
    return Letter(**data)


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield LetterStore(conn)
    conn.close()


def test_store_satisfies_repository_protocol(store):
    assert isinstance(store, LetterRepository)


def test_save_then_get_roundtrip(store):
    letter = _letter()
    store.save(letter)
    assert store.get("cand-1:off1") == letter


def test_get_absent_returns_none(store):
    assert store.get("inconnue") is None


def test_save_is_upsert_no_duplicate(store):
    store.save(_letter(body="Première version du corps, générée par le modèle."))
    store.save(
        _letter(
            body="Seconde version, cette fois éditée à la main par le candidat.",
            source=SOURCE_HUMAN,
            model="",
            updated_at="t1",
        )
    )
    assert store.count() == 1
    got = store.get("cand-1:off1")
    assert got.source == SOURCE_HUMAN
    assert "Seconde version" in got.body
    assert got.updated_at == "t1"


def test_delete_returns_true_then_false(store):
    store.save(_letter())
    assert store.delete("cand-1:off1") is True
    assert store.get("cand-1:off1") is None
    # Idempotence : re-supprimer une lettre absente ne lève pas, renvoie False.
    assert store.delete("cand-1:off1") is False
