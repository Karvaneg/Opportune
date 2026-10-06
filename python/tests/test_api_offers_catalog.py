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
                       created_at="2026-03-01T00:00:00+00:00"))  # faible → 0


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
