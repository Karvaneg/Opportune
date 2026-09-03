"""Tests du service de recommandation d'opportunités (OPP-0393).

Vrais dépôts SQLite en mémoire : aucun réseau, aucune I/O disque.
"""

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import (
    OfferRecommendation,
    RecommendationService,
    UnknownCandidateError,
)


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
    pconn = connect(":memory:")
    oconn = connect(":memory:")
    profiles = ProfileStore(pconn)
    offers = OfferStore(oconn)
    profile = create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    )
    profiles.save(profile)
    service = RecommendationService(profiles, offers)
    yield service, offers
    pconn.close()
    oconn.close()


def _seed_three(offers):
    offers.save(_offer(id="a", title="A", url="http://a"))  # parfaite → 100
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"]))  # 1/2 → 78
    offers.save(_offer(  # faible → 0
        id="c", title="C", url="http://c", skills=["Java"],
        contract_type="Freelance", location="Lyon", seniority="Lead",
    ))


def test_recommend_ranks_by_score_desc(env):
    service, offers = env
    _seed_three(offers)
    recos = service.recommend("cand-1")
    assert [(r.offer.id, r.score) for r in recos] == [("a", 100), ("b", 78), ("c", 0)]


def test_recommend_filters_by_min_score(env):
    service, offers = env
    _seed_three(offers)
    recos = service.recommend("cand-1", min_score=50)
    assert [r.offer.id for r in recos] == ["a", "b"]  # c (0) écartée


def test_recommend_respects_limit(env):
    service, offers = env
    _seed_three(offers)
    assert [r.offer.id for r in service.recommend("cand-1", limit=1)] == ["a"]


def test_recommend_excludes_non_evaluable_offers(env):
    service, offers = env
    offers.save(_offer(id="a", title="A", url="http://a"))  # évaluable → 100
    offers.save(_offer(  # rien d'évaluable → score None → exclue
        id="d", title="D", url="http://d", skills=[], contract_type="",
        location="", seniority="Non précisé",
    ))
    recos = service.recommend("cand-1")
    assert [r.offer.id for r in recos] == ["a"]


def test_recommendation_content(env):
    service, offers = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    reco = service.recommend("cand-1")[0]
    assert isinstance(reco, OfferRecommendation)
    assert reco.score == 100
    assert reco.action == "postuler"
    assert reco.matched  # critères correspondants présents
    assert reco.gaps == []  # aucun écart
    assert "Score 100/100" in reco.justification
    assert "A" in reco.justification


def test_unknown_candidate_raises(env):
    service, _ = env
    with pytest.raises(UnknownCandidateError):
        service.recommend("nope")


def test_negative_limit_rejected(env):
    service, offers = env
    _seed_three(offers)
    with pytest.raises(ValueError):
        service.recommend("cand-1", limit=-1)


def test_empty_stock_returns_empty(env):
    service, _ = env
    assert service.recommend("cand-1") == []
