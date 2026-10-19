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
    OfferCatalogEntry,
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


# Dates d'ingestion explicites et croissantes a < b < c : l'ordre par **date décroissante**
# (OPP-152) est ainsi c, b, a — l'inverse du score (a=100, b=78, c=0) — ce qui prouve que
# l'ordre suit la date et non le score.
def _seed_three(offers):
    offers.save(_offer(id="a", title="A", url="http://a",
                       created_at="2026-01-01T00:00:00+00:00"))  # parfaite → 100, plus ancienne
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"],
                       created_at="2026-01-02T00:00:00+00:00"))  # 1/2 → 78
    offers.save(_offer(  # faible → 0, plus récente
        id="c", title="C", url="http://c", skills=["Java"],
        contract_type="Freelance", location="Lyon", seniority="Lead",
        created_at="2026-01-03T00:00:00+00:00",
    ))


def test_recommend_ranks_by_date_desc(env):
    # OPP-152 : plus récentes d'abord (c, b, a), pas par score — mais le score reste attaché.
    service, offers = env
    _seed_three(offers)
    recos = service.recommend("cand-1")
    assert [(r.offer.id, r.score) for r in recos] == [("c", 0), ("b", 78), ("a", 100)]


def test_recommend_filters_by_min_score(env):
    service, offers = env
    _seed_three(offers)
    recos = service.recommend("cand-1", min_score=50)
    assert [r.offer.id for r in recos] == ["b", "a"]  # c (0) écartée ; ordre par date desc


def test_recommend_respects_limit(env):
    service, offers = env
    _seed_three(offers)
    assert [r.offer.id for r in service.recommend("cand-1", limit=1)] == ["c"]  # la plus récente


def test_recommend_excludes_non_evaluable_offers(env):
    service, offers = env
    offers.save(_offer(id="a", title="A", url="http://a"))  # évaluable → 100
    offers.save(_offer(  # rien d'évaluable → score None → exclue
        id="d", title="D", url="http://d", skills=[], contract_type="",
        location="", seniority="Non précisé",
    ))
    recos = service.recommend("cand-1")
    assert [r.offer.id for r in recos] == ["a"]


def test_recommend_excludes_formations(env):
    # OPP-166 : une formation n'est pas scorée comme un emploi → non classable, hors reco.
    service, offers = env
    offers.save(_offer(id="a", title="A", url="http://a"))  # emploi évaluable → 100
    offers.save(_offer(id="f", title="Formation Python", url="http://f", kind="formation"))
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


def test_recommend_excludes_given_offer_ids(env):
    # OPP-150 : les offres déjà traitées (ids exclus) sont ignorées avant tout scoring.
    service, offers = env
    _seed_three(offers)
    recos = service.recommend("cand-1", exclude_offer_ids={"a", "b"})
    assert [r.offer.id for r in recos] == ["c"]


def test_recommend_one_returns_single_recommendation(env):
    service, offers = env
    _seed_three(offers)
    reco = service.recommend_one("cand-1", "b")
    assert isinstance(reco, OfferRecommendation)
    assert reco.offer.id == "b"
    assert reco.score == 78


def test_recommend_one_none_when_offer_absent(env):
    service, offers = env
    _seed_three(offers)
    assert service.recommend_one("cand-1", "does-not-exist") is None


def test_recommend_one_none_when_offer_not_evaluable(env):
    service, offers = env
    offers.save(_offer(  # rien d'évaluable → score None
        id="d", title="D", url="http://d", skills=[], contract_type="",
        location="", seniority="Non précisé",
    ))
    assert service.recommend_one("cand-1", "d") is None


def test_recommend_one_returns_unscored_recommendation_for_formation(env):
    # OPP-166 : ouvrir une formation produit bien une recommandation (donc une fiche décidable),
    # mais SANS score d'adéquation (action indéterminée) — candidater à une formation a du sens.
    service, offers = env
    offers.save(_offer(id="f", title="Bootcamp Data", url="http://f", kind="formation"))
    reco = service.recommend_one("cand-1", "f")
    assert reco is not None
    assert reco.score is None
    assert reco.action == "indeterminee"
    assert reco.matched == [] and reco.gaps == []
    assert "Formation" in reco.justification


def test_recommend_one_unknown_candidate_raises(env):
    service, offers = env
    _seed_three(offers)
    with pytest.raises(UnknownCandidateError):
        service.recommend_one("nope", "a")


# --- Catalogue paginé + score de match (OPP-146) ------------------------------


def test_list_catalog_annotates_scores_in_date_order(env):
    service, offers = env
    _seed_three(offers)  # a=100, b=78, c=0 ; dates a<b<c → ordre c, b, a
    entries, total = service.list_catalog(candidate_id="cand-1")
    assert total == 3
    assert [(e.offer.id, e.score) for e in entries] == [("c", 0), ("b", 78), ("a", 100)]
    assert all(isinstance(e, OfferCatalogEntry) for e in entries)
    # La bande de reco accompagne le score (source unique des seuils, OPP-146).
    assert [e.action for e in entries] == ["ignorer", "a_etudier", "postuler"]


def test_list_catalog_without_candidate_has_no_scores(env):
    service, offers = env
    _seed_three(offers)
    entries, total = service.list_catalog()  # pas de candidat → catalogue brut
    assert total == 3
    assert [e.offer.id for e in entries] == ["c", "b", "a"]  # toujours trié par date
    assert all(e.score is None and e.action is None for e in entries)


def test_list_catalog_non_evaluable_offer_scored_none(env):
    service, offers = env
    offers.save(_offer(  # aucune dimension mesurable → score None (mais listée)
        id="d", title="D", url="http://d", skills=[], contract_type="",
        location="", seniority="Non précisé", created_at="2026-01-01T00:00:00+00:00",
    ))
    entries, total = service.list_catalog(candidate_id="cand-1")
    assert total == 1
    assert entries[0].offer.id == "d" and entries[0].score is None and entries[0].action is None


def test_list_catalog_lists_formation_without_score(env):
    # OPP-166 : une formation reste visible au catalogue, mais sans score ni bande de reco
    # (le front s'appuie sur ``offer.kind`` pour afficher le badge « Formation »).
    service, offers = env
    offers.save(_offer(id="f", title="Formation ISTQB", url="http://f", kind="formation",
                       created_at="2026-01-01T00:00:00+00:00"))
    entries, total = service.list_catalog(candidate_id="cand-1")
    assert total == 1
    assert entries[0].offer.kind == "formation"
    assert entries[0].score is None and entries[0].action is None


def test_list_catalog_paginates(env):
    service, offers = env
    _seed_three(offers)  # ordre date desc : c, b, a
    page1, total = service.list_catalog(candidate_id="cand-1", limit=2, offset=0)
    page2, _ = service.list_catalog(candidate_id="cand-1", limit=2, offset=2)
    assert total == 3
    assert [e.offer.id for e in page1] == ["c", "b"]
    assert [e.offer.id for e in page2] == ["a"]


def test_list_catalog_unknown_candidate_raises(env):
    service, offers = env
    _seed_three(offers)
    with pytest.raises(UnknownCandidateError):
        service.list_catalog(candidate_id="nope")
