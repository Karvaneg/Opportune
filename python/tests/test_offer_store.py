"""Tests de la persistance SQLite des offres (OPP-037).

Base SQLite en mémoire (``:memory:``) : aucune I/O disque, aucun réseau.
"""

import hashlib

import pytest

from app.db import connect
from app.offer import Offer, compute_offer_id
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
        # Date explicite → préservée par save (qui n'horodate que si created_at est vide),
        # pour que les round-trips d'égalité restent déterministes.
        created_at="2026-01-01T00:00:00+00:00",
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


def test_list_all_returns_every_offer(store):
    store.save(_offer(id="b"))
    store.save(_offer(id="a"))
    offers = store.list_all()
    # Dates égales (même created_at par défaut) → tie-break par id ascendant.
    assert [o.id for o in offers] == ["a", "b"]
    assert all(isinstance(o.skills, list) for o in offers)


def test_list_all_orders_by_date_desc(store):
    # OPP-152 : plus récentes d'abord, indépendamment de l'id.
    store.save(_offer(id="a", created_at="2026-01-01T00:00:00+00:00"))
    store.save(_offer(id="b", created_at="2026-03-01T00:00:00+00:00"))
    store.save(_offer(id="c", created_at="2026-02-01T00:00:00+00:00"))
    assert [o.id for o in store.list_all()] == ["b", "c", "a"]


def test_save_stamps_created_at_when_absent(store):
    # Cas nominal (from_analysis) : created_at vide → horodaté à l'insertion.
    store.save(_offer(created_at=""))
    assert store.get("abc123").created_at != ""


def test_save_preserves_first_created_at_on_upsert(store):
    # OPP-152 : recoller/ré-ingérer ne remonte pas la date (première ingestion conservée).
    store.save(_offer(created_at="2026-01-01T00:00:00+00:00"))
    store.save(_offer(created_at="2026-09-09T00:00:00+00:00", summary="v2"))
    fetched = store.get("abc123")
    assert fetched.summary == "v2"  # le reste est bien mis à jour
    assert fetched.created_at == "2026-01-01T00:00:00+00:00"  # mais pas la date


def test_list_all_empty(store):
    assert store.list_all() == []


def test_list_paginates_in_date_order(store):
    # OPP-146 : page d'offres, plus récentes d'abord, découpée par limit/offset.
    store.save(_offer(id="a", created_at="2026-01-01T00:00:00+00:00"))
    store.save(_offer(id="b", created_at="2026-02-01T00:00:00+00:00"))
    store.save(_offer(id="c", created_at="2026-03-01T00:00:00+00:00"))
    assert [o.id for o in store.list(limit=2, offset=0)] == ["c", "b"]  # 1re page
    assert [o.id for o in store.list(limit=2, offset=2)] == ["a"]        # 2e page
    assert store.count() == 3


def test_migrates_legacy_table_without_created_at():
    # Base antérieure à OPP-152 : table offers sans created_at + une ligne. L'ouverture par
    # OfferStore doit ajouter la colonne et dater la ligne existante (backfill), sans planter.
    conn = connect(":memory:")
    conn.execute(
        "CREATE TABLE offers ("
        "id TEXT PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL, "
        "location TEXT NOT NULL, skills TEXT NOT NULL, seniority TEXT NOT NULL, "
        "contract_type TEXT NOT NULL, summary TEXT NOT NULL, attention_points TEXT NOT NULL, "
        "source TEXT NOT NULL, url TEXT NOT NULL, raw_text TEXT NOT NULL)"
    )
    # Id dérivé du schéma (une vraie ligne historique n'a jamais un id littéral) : pour
    # ``http://x``, la forme canonique vaut l'ancienne → la migration d'id (OPP-119) est un
    # no-op et ce test reste focalisé sur le seul backfill ``created_at``.
    legacy_id = compute_offer_id("indeed", "http://x", "t")
    conn.execute(
        "INSERT INTO offers VALUES "
        "(?,'Dev','Acme','Paris','[]','Senior','CDI','s','[]','indeed','http://x','t')",
        (legacy_id,),
    )
    conn.commit()

    store = OfferStore(conn)  # déclenche la migration
    fetched = store.get(legacy_id)
    assert fetched is not None
    assert fetched.created_at != ""  # ligne historique datée (backfill)
    conn.close()


def test_migrates_legacy_offer_ids_to_canonical_scheme():
    # Offre ingérée avant OPP-119 : id dérivé du schéma ancien (URL minusculée en entier,
    # slash final conservé). L'ouverture doit recaler l'id sur le schéma canonique courant,
    # pour que la ré-ingestion de la même URL upsert au lieu de dupliquer.
    conn = connect(":memory:")
    OfferStore(conn)  # crée la table au schéma courant
    url = "https://x.com/Job/42/"
    legacy_id = hashlib.sha256(
        ("indeed\n" + url.strip().lower()).encode("utf-8")
    ).hexdigest()[:16]
    conn.execute(
        "INSERT INTO offers (id, title, company, location, skills, seniority, "
        "contract_type, summary, attention_points, source, url, raw_text, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (legacy_id, "Dev", "Acme", "Paris", "[]", "Senior", "CDI", "s", "[]",
         "indeed", url, "t", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()

    OfferStore(conn)  # ré-ouverture → migration des id
    canonical_id = compute_offer_id("indeed", url, "t")
    assert canonical_id != legacy_id  # le schéma a bien changé
    assert store_get(conn, canonical_id) is not None
    assert store_get(conn, legacy_id) is None
    conn.close()


def test_migrates_legacy_ids_merging_collisions_keeps_oldest():
    # Deux liens de la MÊME offre (slash final) stockés sous deux id anciens distincts :
    # la migration les fusionne vers l'unique id canonique, la plus ancienne faisant foi.
    conn = connect(":memory:")
    OfferStore(conn)
    for url, created in (
        ("https://x.com/job/9", "2026-01-01T00:00:00+00:00"),   # plus ancienne
        ("https://x.com/job/9/", "2026-02-01T00:00:00+00:00"),  # doublon plus récent
    ):
        legacy_id = hashlib.sha256(
            ("indeed\n" + url.strip().lower()).encode("utf-8")
        ).hexdigest()[:16]
        conn.execute(
            "INSERT INTO offers (id, title, company, location, skills, seniority, "
            "contract_type, summary, attention_points, source, url, raw_text, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (legacy_id, "Dev", "Acme", "Paris", "[]", "Senior", "CDI", "s", "[]",
             "indeed", url, "t", created),
        )
    conn.commit()

    store = OfferStore(conn)  # migration + fusion
    assert store.count() == 1
    survivor = store.get(compute_offer_id("indeed", "https://x.com/job/9", "t"))
    assert survivor is not None
    assert survivor.created_at == "2026-01-01T00:00:00+00:00"  # la plus ancienne survit
    conn.close()


def store_get(conn, offer_id):
    return conn.execute("SELECT 1 FROM offers WHERE id = ?", (offer_id,)).fetchone()
