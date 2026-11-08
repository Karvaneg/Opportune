"""Tests de l'appartenance des offres aux recherches (OPP-186).

Base SQLite en mémoire : aucune I/O disque, aucun réseau.
"""

from app.candidate_offer_store import CandidateOfferStore, remap_offer_id
from app.candidate_registry import CandidateRegistry
from app.db import connect
from app.offer import Offer, compute_offer_id
from app.offer_store import OfferStore


def _offer(offer_id: str, created_at: str = "2026-01-01T00:00:00+00:00") -> Offer:
    return Offer(
        id=offer_id,
        title=f"Offre {offer_id}",
        company="Acme",
        location="Paris",
        skills=["Python"],
        seniority="Senior",
        contract_type="CDI",
        summary="s",
        attention_points=[],
        source="indeed",
        url=f"http://{offer_id}",
        raw_text="t",
        created_at=created_at,
    )


def _stores():
    conn = connect(":memory:")
    offers = OfferStore(conn)
    CandidateRegistry(conn)
    return conn, offers, CandidateOfferStore(conn)


def test_link_makes_offer_visible_to_that_search_only():
    _, offers, links = _stores()
    offers.save(_offer("o1"))

    links.link("cand-a", "o1")

    assert links.is_linked("cand-a", "o1")
    assert not links.is_linked("cand-b", "o1")
    assert links.offer_ids("cand-a") == ["o1"]
    assert links.offer_ids("cand-b") == []


def test_link_is_idempotent():
    _, offers, links = _stores()
    offers.save(_offer("o1"))

    links.link("cand-a", "o1")
    links.link("cand-a", "o1")

    assert links.count("cand-a") == 1


def test_offer_ids_most_recent_first_and_paginated():
    _, offers, links = _stores()
    for offer_id, day in (("old", "01"), ("mid", "02"), ("new", "03")):
        offers.save(_offer(offer_id, created_at=f"2026-01-{day}T00:00:00+00:00"))
        links.link("cand-a", offer_id)

    all_ids = links.offer_ids("cand-a")
    second_page = links.offer_ids("cand-a", limit=2, offset=2)

    assert all_ids == ["new", "mid", "old"]
    assert second_page == ["old"]


def test_link_to_missing_offer_is_neither_listed_nor_counted():
    _, _, links = _stores()

    links.link("cand-a", "absente")

    assert links.offer_ids("cand-a") == []
    assert links.count("cand-a") == 0


def test_creation_links_existing_offers_to_every_existing_search():
    conn = connect(":memory:")
    offers = OfferStore(conn)
    registry = CandidateRegistry(conn)
    offers.save(_offer("o1"))
    offers.save(_offer("o2"))
    registry.add("cand-a")
    registry.add("cand-b")

    links = CandidateOfferStore(conn)

    assert sorted(links.offer_ids("cand-a")) == ["o1", "o2"]
    assert sorted(links.offer_ids("cand-b")) == ["o1", "o2"]


def test_search_created_after_migration_starts_without_offers():
    conn = connect(":memory:")
    offers = OfferStore(conn)
    registry = CandidateRegistry(conn)
    offers.save(_offer("o1"))
    registry.add("cand-a")
    CandidateOfferStore(conn)
    registry.add("cand-new")

    links = CandidateOfferStore(conn)  # réouverture : la migration ne se rejoue pas

    assert links.offer_ids("cand-a") == ["o1"]
    assert links.offer_ids("cand-new") == []


def test_creation_without_offers_or_searches_tables_links_nothing():
    conn = connect(":memory:")

    links = CandidateOfferStore(conn)

    OfferStore(conn).save(_offer("o1"))
    assert links.offer_ids("cand-a") == []


def test_remap_offer_id_moves_links_to_the_new_id():
    conn, offers, links = _stores()
    offers.save(_offer("new"))
    links.link("cand-a", "old")
    links.link("cand-b", "old")
    links.link("cand-b", "new")

    remap_offer_id(conn, "old", "new")

    assert links.offer_ids("cand-a") == ["new"]
    assert links.offer_ids("cand-b") == ["new"]
    assert links.count("cand-b") == 1


def test_remap_offer_id_without_links_table_does_nothing():
    conn = connect(":memory:")

    remap_offer_id(conn, "old", "new")

    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "candidate_offers" not in tables


def test_offer_store_id_migration_keeps_the_offer_in_its_search():
    # Une offre stockée sous un id d'un ancien schéma (OPP-119) change d'id à la réouverture
    # d'``OfferStore`` : son lien doit la suivre, sinon elle disparaît de la recherche.
    conn, offers, links = _stores()
    offers.save(_offer("o1"))
    conn.execute("UPDATE offers SET id = 'ancien-id' WHERE id = 'o1'")
    links.link("cand-a", "ancien-id")
    expected_id = compute_offer_id("indeed", "http://o1", "t")

    OfferStore(conn)

    assert links.offer_ids("cand-a") == [expected_id]


def test_offer_linked_late_comes_first_for_that_search():
    # Revue OPP-186 : une offre déjà ancienne en base, rattachée aujourd'hui à une recherche, est
    # une entrée récente pour celle-ci. Le tri suit la date du lien, pas celle de l'offre.
    conn, offers, links = _stores()
    offers.save(_offer("z-ancienne", created_at="2025-01-01T00:00:00+00:00"))
    offers.save(_offer("a-recente", created_at="2026-06-01T00:00:00+00:00"))
    links.link("cand-b", "a-recente")
    conn.execute(
        "UPDATE candidate_offers SET created_at = '2026-06-01T00:00:00+00:00' "
        "WHERE offer_id = 'a-recente'"
    )
    links.link("cand-b", "z-ancienne")

    ids = links.offer_ids("cand-b")

    assert ids == ["z-ancienne", "a-recente"]


def test_links_return_the_date_the_offer_entered_the_search():
    _, offers, links = _stores()
    offers.save(_offer("o1", created_at="2025-01-01T00:00:00+00:00"))

    links.link("cand-a", "o1")

    [(offer_id, entered_at)] = links.links("cand-a")
    assert offer_id == "o1"
    assert entered_at > "2025-01-01T00:00:00+00:00"


def test_migration_dates_each_link_with_the_offer_date():
    conn = connect(":memory:")
    offers = OfferStore(conn)
    CandidateRegistry(conn).add("cand-a")
    offers.save(_offer("o1", created_at="2025-01-01T00:00:00+00:00"))

    links = CandidateOfferStore(conn)

    assert links.links("cand-a") == [("o1", "2025-01-01T00:00:00+00:00")]
