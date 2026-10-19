"""Tests de l'endpoint catalogue ``GET /offers`` (OPP-146).

Vrais dépôts SQLite en mémoire ; aucun réseau. On vérifie le contrat HTTP : pagination,
tri par date, annotation du score via ``?candidate_id`` et gardes (401 / owner-gating 404).
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, AuthProvider, User
from app.candidate_profile import create_profile
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _offer(**overrides) -> Offer:
    data = dict(
        id="o", title="Offre", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


def _seed_three(offers):
    # Dates croissantes a < b < c → ordre par date décroissante c, b, a.
    offers.save(_offer(id="a", title="A", url="http://a",
                       created_at="2026-01-01T00:00:00+00:00"))  # parfaite → 100
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"],
                       created_at="2026-02-01T00:00:00+00:00"))  # 1/2 → 78
    offers.save(_offer(id="c", title="C", url="http://c", skills=["Java"],
                       contract_type="Freelance", location="Lyon", seniority="Lead",
                       created_at="2026-03-01T00:00:00+00:00"))  # faible → 11 (séniorité 6/8 graduée)


def _build(*, auth=None):
    conn = connect(":memory:")
    offers = OfferStore(conn)
    profiles = ProfileStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=auth), offers


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_offers_lists_paginated_in_date_order():
    api, offers = _build()
    _seed_three(offers)
    resp = api.dispatch("GET", "/offers")
    assert resp.status == 200
    assert [i["id"] for i in resp.body["items"]] == ["c", "b", "a"]  # récentes d'abord
    assert resp.body["total"] == 3
    assert resp.body["page"] == 1 and resp.body["total_pages"] == 1
    # Sans candidat : aucun score annoté.
    assert all(i["score"] is None for i in resp.body["items"])


def test_get_offers_annotates_score_for_candidate():
    api, offers = _build()
    _seed_three(offers)
    resp = api.dispatch("GET", "/offers?candidate_id=cand-1")
    assert resp.status == 200
    assert [(i["id"], i["score"]) for i in resp.body["items"]] == [
        ("c", 0), ("b", 78), ("a", 100),
    ]
    # La bande de reco pilote l'affichage côté client (seuils serveur, pas de duplication).
    assert [i["action"] for i in resp.body["items"]] == ["ignorer", "a_etudier", "postuler"]


def test_get_offers_exposes_kind_and_leaves_formation_unscored():
    # OPP-166 : le catalogue expose ``kind`` ; une formation est listée mais sans score ni
    # bande de reco, même avec un candidat ciblé (le front badge « Formation »).
    api, offers = _build()
    offers.save(_offer(id="a", title="A", url="http://a"))  # emploi → scoré
    offers.save(_offer(id="f", title="Formation ISTQB", url="http://f", kind="formation"))
    resp = api.dispatch("GET", "/offers?candidate_id=cand-1")
    assert resp.status == 200
    by_id = {i["id"]: i for i in resp.body["items"]}
    assert by_id["a"]["kind"] == "emploi" and by_id["a"]["score"] is not None
    assert by_id["f"]["kind"] == "formation"
    assert by_id["f"]["score"] is None and by_id["f"]["action"] is None


def test_get_offers_respects_pagination_params():
    api, offers = _build()
    _seed_three(offers)
    resp = api.dispatch("GET", "/offers?page=2&page_size=2")
    assert resp.status == 200
    assert [i["id"] for i in resp.body["items"]] == ["a"]  # 2e page
    assert resp.body["total"] == 3 and resp.body["total_pages"] == 2


@pytest.mark.parametrize("qs", ["page=0", "page_size=0", "page_size=101", "page=x"])
def test_get_offers_rejects_bad_pagination(qs):
    api, offers = _build()
    assert api.dispatch("GET", f"/offers?{qs}").status == 400


def test_get_offers_filters_by_funnel_stage():
    # OPP-164 : ?stage= découpe tout le pool AVANT pagination (côté serveur), pour que total
    # et pagination concordent avec les compteurs du cockpit. Piloté par la décision, pas le score.
    api, offers = _build()
    _seed_three(offers)
    api.orchestrator.rescore_offer("cand-1", "c")  # c = score faible (algo : ignorer)
    api.orchestrator.validate_decision("cand-1", "c", "approved")  # … mais approuvée → à postuler

    postuler = api.dispatch("GET", "/offers?candidate_id=cand-1&stage=a_postuler")
    assert postuler.status == 200
    assert [i["id"] for i in postuler.body["items"]] == ["c"]
    assert postuler.body["total"] == 1

    etudier = api.dispatch("GET", "/offers?candidate_id=cand-1&stage=a_etudier")
    assert [i["id"] for i in etudier.body["items"]] == ["b", "a"]  # non décidées, récentes d'abord
    assert etudier.body["total"] == 2


def test_get_offers_stage_filter_paginates_subset():
    # Le filtre précède la pagination : page_size=1 sur les 3 offres « à étudier » → 3 pages.
    api, offers = _build()
    _seed_three(offers)
    page1 = api.dispatch("GET", "/offers?candidate_id=cand-1&stage=a_etudier&page_size=1")
    assert [i["id"] for i in page1.body["items"]] == ["c"]
    assert page1.body["total"] == 3 and page1.body["total_pages"] == 3
    page2 = api.dispatch("GET", "/offers?candidate_id=cand-1&stage=a_etudier&page_size=1&page=2")
    assert [i["id"] for i in page2.body["items"]] == ["b"]


def test_get_offers_unknown_or_candidateless_stage_is_ignored():
    # Un stage inconnu, ou sans candidat ciblé, → catalogue complet (aligné sur le front, qui
    # ignore un param d'étape invalide). On ne filtre jamais un pool sans état décisionnel.
    api, offers = _build()
    _seed_three(offers)
    bogus = api.dispatch("GET", "/offers?candidate_id=cand-1&stage=bogus")
    assert [i["id"] for i in bogus.body["items"]] == ["c", "b", "a"] and bogus.body["total"] == 3
    no_cand = api.dispatch("GET", "/offers?stage=a_postuler")
    assert no_cand.body["total"] == 3  # pas de candidat → filtre ignoré


def test_get_offers_requires_authentication():
    auth = AuthProvider({"tok": User("u", REVIEWER, frozenset({"cand-1"}))})
    api, _ = _build(auth=auth)
    assert api.dispatch("GET", "/offers").status == 401  # pas de jeton
    assert api.dispatch("GET", "/offers", None, _hdr("tok")).status == 200


def test_get_offers_candidate_owner_gated():
    auth = AuthProvider({"tok": User("u", REVIEWER, frozenset({"cand-1"}))})
    api, offers = _build(auth=auth)
    _seed_three(offers)
    # Candidat possédé : OK + scores.
    ok = api.dispatch("GET", "/offers?candidate_id=cand-1", None, _hdr("tok"))
    assert ok.status == 200 and ok.body["items"][0]["score"] is not None
    # Candidat d'autrui : 404 neutre (anti-énumération), on ne note jamais pour lui.
    assert api.dispatch("GET", "/offers?candidate_id=autre", None, _hdr("tok")).status == 404
