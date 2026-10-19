"""Tests de la persistance SQLite des décisions (OPP-057).

Base SQLite en mémoire : aucune I/O disque, aucun réseau.
"""

import pytest

from app.db import connect
from app.decision import create_decision, validate
from app.decision_store import DecisionRepository, DecisionStore


def _decision(candidate_id="cand-1", offer_id="off-1"):
    return create_decision(
        candidate_id=candidate_id, offer_id=offer_id, action="postuler",
        score=90, justification="Score 90/100.", now=lambda: "t0",
    )


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield DecisionStore(conn)
    conn.close()


def test_store_satisfies_repository_protocol(store):
    assert isinstance(store, DecisionRepository)


def test_save_then_get_roundtrip_including_history(store):
    d = validate(_decision(), "approved", comment="ok", now=lambda: "t1")
    store.save(d)
    fetched = store.get("cand-1:off-1")
    assert fetched == d  # égalité dataclass, historique restauré
    assert fetched.history[-1].status == "approved"
    assert fetched.history[-1].comment == "ok"


def test_get_unknown_returns_none(store):
    assert store.get("nope") is None


def test_save_is_an_upsert_preserving_identity(store):
    store.save(_decision())  # pending
    store.save(validate(_decision(), "rejected", now=lambda: "t1"))  # même id
    assert store.count() == 1
    assert store.get("cand-1:off-1").status == "rejected"


def test_list_for_candidate(store):
    store.save(_decision(candidate_id="c", offer_id="o1"))
    store.save(_decision(candidate_id="c", offer_id="o2"))
    store.save(_decision(candidate_id="autre", offer_id="o3"))
    decisions = store.list_for_candidate("c")
    assert [d.offer_id for d in decisions] == ["o1", "o2"]


def test_optional_comment_persists_as_null(store):
    store.save(_decision())  # pending, sans commentaire
    assert store.get("cand-1:off-1").comment is None


def test_formation_decision_persists_null_score(store):
    # OPP-166 : une décision de formation (score None) est persistée et relue sans contrainte.
    decision = create_decision(
        candidate_id="cand-1", offer_id="f", action="indeterminee",
        score=None, justification="Formation : non évaluée.", now=lambda: "t0",
    )
    store.save(decision)
    assert store.get("cand-1:f").score is None


def test_migrates_legacy_not_null_score_to_nullable():
    # Base antérieure à OPP-166 : colonne score NOT NULL. L'ouverture doit reconstruire la
    # table en nullable (en préservant les lignes existantes), pour accepter une formation.
    conn = connect(":memory:")
    conn.execute(
        "CREATE TABLE decisions ("
        "id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, offer_id TEXT NOT NULL, "
        "action TEXT NOT NULL, score INTEGER NOT NULL, justification TEXT NOT NULL, "
        "status TEXT NOT NULL, comment TEXT, history TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO decisions VALUES "
        "('cand-1:a','cand-1','a','postuler',100,'j','pending',NULL,'[]')"
    )
    conn.commit()

    store = DecisionStore(conn)  # déclenche la migration (reconstruction nullable)
    assert store.get("cand-1:a").score == 100  # ligne préservée
    # La contrainte est levée : une formation (score None) passe désormais.
    store.save(create_decision(
        candidate_id="cand-1", offer_id="f", action="indeterminee",
        score=None, justification="Formation.", now=lambda: "t0",
    ))
    assert store.get("cand-1:f").score is None
    conn.close()
