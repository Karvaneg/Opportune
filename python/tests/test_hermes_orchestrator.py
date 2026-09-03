"""Tests de l'orchestrateur Hermes (OPP-060).

Vrais dépôts SQLite en mémoire : aucun réseau, aucune I/O disque. Hermes coordonne
``RecommendationService`` et ``DecisionStore`` ; on vérifie le câblage (ordre, décisions
persistées, propagation d'erreurs), pas la logique déléguée (déjà couverte ailleurs).
"""

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.decision import DecisionError, PENDING, decision_id
from app.decision_service import DecisionService, UnknownDecisionError
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService, UnknownCandidateError

from hermes.models import HermesRecommendation
from hermes.orchestrator import HermesOrchestrator


def _offer(**overrides) -> Offer:
    data = dict(
        id="o", title="Offre", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


@pytest.fixture
def env():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decisions = DecisionStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    service = RecommendationService(profiles, offers)
    decision_service = DecisionService(decisions, now=lambda: "2026-09-03T00:00:00+00:00")
    orchestrator = HermesOrchestrator(service, decision_service)
    yield orchestrator, offers, decisions
    conn.close()


def _seed_three(offers):
    offers.save(_offer(id="a", title="A", url="http://a"))  # parfaite → 100
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"]))  # → 78
    offers.save(_offer(  # faible → 0
        id="c", title="C", url="http://c", skills=["Java"],
        contract_type="Freelance", location="Lyon", seniority="Lead",
    ))


def test_returns_recommendations_ordered_by_score(env):
    orchestrator, offers, _ = env
    _seed_three(offers)
    results = orchestrator.recommend_for_candidate("cand-1")
    assert all(isinstance(r, HermesRecommendation) for r in results)
    assert [(r.recommendation.offer.id, r.recommendation.score) for r in results] == [
        ("a", 100), ("b", 78), ("c", 0),
    ]


def test_creates_and_persists_a_pending_decision_per_recommendation(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    results = orchestrator.recommend_for_candidate("cand-1")
    assert decisions.count() == 3
    for r in results:
        stored = decisions.get(decision_id("cand-1", r.recommendation.offer.id))
        assert stored is not None
        assert stored == r.decision
        assert stored.status == PENDING
        # La décision reprend fidèlement la recommandation (rien de réimplémenté).
        assert stored.action == r.recommendation.action
        assert stored.score == r.recommendation.score
        assert stored.justification == r.recommendation.justification


def test_respects_limit(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    results = orchestrator.recommend_for_candidate("cand-1", limit=1)
    assert [r.recommendation.offer.id for r in results] == ["a"]
    assert decisions.count() == 1  # seules les décisions retenues sont persistées


def test_unknown_candidate_raises_and_persists_nothing(env):
    orchestrator, _, decisions = env
    with pytest.raises(UnknownCandidateError):
        orchestrator.recommend_for_candidate("nope")
    assert decisions.count() == 0


def test_negative_limit_rejected_and_persists_nothing(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    with pytest.raises(ValueError):
        orchestrator.recommend_for_candidate("cand-1", limit=-1)
    assert decisions.count() == 0


def test_validate_decision_applies_human_status(env):
    orchestrator, offers, decisions = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    orchestrator.recommend_for_candidate("cand-1")  # crée la décision pending
    updated = orchestrator.validate_decision("cand-1", "a", "approved", comment="go")
    assert updated.status == "approved"
    assert updated.comment == "go"
    assert decisions.get(decision_id("cand-1", "a")).status == "approved"


def test_validate_decision_unknown_raises(env):
    orchestrator, _, _ = env
    with pytest.raises(UnknownDecisionError):
        orchestrator.validate_decision("cand-1", "a", "approved")


def test_validate_decision_invalid_status_raises(env):
    orchestrator, offers, _ = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    orchestrator.recommend_for_candidate("cand-1")
    with pytest.raises(DecisionError):
        orchestrator.validate_decision("cand-1", "a", "pending")


def test_empty_stock_returns_empty(env):
    orchestrator, _, decisions = env
    assert orchestrator.recommend_for_candidate("cand-1") == []
    assert decisions.count() == 0


def test_rerun_upserts_decisions_without_duplicating(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    orchestrator.recommend_for_candidate("cand-1")
    orchestrator.recommend_for_candidate("cand-1")  # même candidat, mêmes offres
    assert decisions.count() == 3  # upsert sur le couple candidat/offre, pas de doublon


def test_injected_clock_stamps_decision_history(env):
    orchestrator, offers, decisions = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    result = orchestrator.recommend_for_candidate("cand-1")[0]
    assert result.decision.history[0].at == "2026-09-03T00:00:00+00:00"
