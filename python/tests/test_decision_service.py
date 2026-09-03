"""Tests du service de décision (OPP-060).

Vrai dépôt SQLite en mémoire : aucun réseau, aucune I/O disque. On vérifie le câblage
création/validation + persistance, pas la logique de décision (couverte par test_decision).
"""

import pytest

from app.db import connect
from app.decision import DecisionError, PENDING, decision_id
from app.decision_service import DecisionService, UnknownDecisionError
from app.decision_store import DecisionStore
from app.offer import Offer
from app.recommendation_service import OfferRecommendation


def _recommendation(**overrides) -> OfferRecommendation:
    offer = Offer(
        id="o", title="Offre", company="Acme", location="Paris",
        skills=["Python"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data = dict(
        offer=offer, score=100, action="postuler", matched=[], gaps=[],
        justification="Score 100/100 — postuler.",
    )
    data.update(overrides)
    return OfferRecommendation(**data)


@pytest.fixture
def env():
    conn = connect(":memory:")
    store = DecisionStore(conn)
    service = DecisionService(store, now=lambda: "2026-09-03T00:00:00+00:00")
    yield service, store
    conn.close()


def test_decide_creates_and_persists_pending_decision(env):
    service, store = env
    decision = service.decide(_recommendation(), "cand-1")
    assert decision.status == PENDING
    assert decision.action == "postuler"
    assert decision.score == 100
    assert decision.justification == "Score 100/100 — postuler."
    assert decision.history[0].at == "2026-09-03T00:00:00+00:00"  # horloge injectée
    stored = store.get(decision_id("cand-1", "o"))
    assert stored == decision


def test_decide_upserts_without_duplicating(env):
    service, store = env
    service.decide(_recommendation(), "cand-1")
    service.decide(_recommendation(), "cand-1")
    assert store.count() == 1


def test_validate_applies_human_status_and_persists(env):
    service, store = env
    service.decide(_recommendation(), "cand-1")
    updated = service.validate("cand-1", "o", "approved", comment="go")
    assert updated.status == "approved"
    assert updated.comment == "go"
    assert store.get(decision_id("cand-1", "o")).status == "approved"
    assert len(updated.history) == 2  # pending + approved


def test_validate_unknown_decision_raises(env):
    service, _ = env
    with pytest.raises(UnknownDecisionError):
        service.validate("cand-1", "o", "approved")


def test_validate_invalid_status_raises(env):
    service, _ = env
    service.decide(_recommendation(), "cand-1")
    with pytest.raises(DecisionError):
        service.validate("cand-1", "o", "pending")  # retour à pending interdit
