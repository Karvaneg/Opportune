"""Tests de la persistance SQLite des offres (OPP-037).

Base SQLite en mémoire (``:memory:``) : aucune I/O disque, aucun réseau.
"""

import pytest

from app.db import connect
from app.offer import Offer
from app.offer_store import OfferRepository, OfferStore


def _offer(**overrides) -> Offer:
    base = dict(
        id="abc123",
        title="Dev",
        company="Acme",
        location="Paris",
        skills=["Python", "SQL"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend.",
        attention_points=["Astreintes"],
        source="indeed",
        url="http://x",
        raw_text="texte brut",
    )
    base.update(overrides)
    return Offer(**base)


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield OfferStore(conn)
    conn.close()


def test_store_satisfies_repository_protocol(store):
    assert isinstance(store, OfferRepository)


def test_save_then_get_roundtrip(store):
    store.save(_offer())
    fetched = store.get("abc123")
    assert fetched == _offer()  # égalité de dataclass, listes JSON restaurées


def test_get_unknown_returns_none(store):
    assert store.get("nope") is None


def test_save_is_an_upsert_not_a_duplicate(store):
    store.save(_offer(summary="v1"))
    store.save(_offer(summary="v2"))  # même id
    assert store.count() == 1
    assert store.get("abc123").summary == "v2"


def test_distinct_ids_coexist(store):
    store.save(_offer(id="a"))
    store.save(_offer(id="b"))
    assert store.count() == 2
