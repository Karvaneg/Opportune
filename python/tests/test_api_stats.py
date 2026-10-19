"""Tests de l'endpoint d'agrégats du cockpit (OPP-163).

``GET /candidates/{id}/stats`` : compteurs pré-calculés, owner-gated, régression transport.
Vrais dépôts SQLite en mémoire ; aucune I/O réseau.
"""

import itertools

import pytest

from api.app import HermesApi
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.auth import REVIEWER, AuthProvider, User
from app.candidate_profile import create_profile
from app.db import connect
from app.decision import decision_id
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
        id="o", title="T", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def env():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decisions_store = DecisionStore(conn)
    applications = ApplicationActionStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    # a → 100 (postuler), b → a_etudier, c → ignorer (mêmes profils que les autres suites).
    offers.save(_offer(id="a", title="A", url="http://a"))
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"]))
    offers.save(_offer(id="c", title="C", url="http://c", skills=["Java"],
                       contract_type="Freelance", location="Lyon", seniority="Lead"))
    decisions = DecisionService(decisions_store, now=lambda: "2026-09-04T00:00:00+00:00")
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers), decisions,
        runs=RunStore(conn), run_id=lambda: "run-1", now=lambda: "2026-09-04T12:00:00+00:00",
    )
    ids = (str(n) for n in itertools.count(1))
    actions = ActionService(
        decisions, applications, OutboundMessageActionStore(conn),
        new_id=lambda: next(ids), now=lambda: "2026-09-05T00:00:00+00:00",
    )
    # rev possède cand-1 (reviewer) ; str est reviewer mais possède un autre périmètre.
    auth = AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-str": User("str", REVIEWER, frozenset({"cand-2"})),
    })
    api = HermesApi(orchestrator, actions, auth)
    yield api
    conn.close()


def test_stats_payload_counts_actionable_and_pool(env):
    resp = env.dispatch("GET", "/candidates/cand-1/stats", None, _hdr("tok-rev"))
    assert resp.status == 200
    assert resp.body == {"a_etudier": 1, "a_postuler": 1, "postule": 0, "offres_total": 3}


def test_stats_coherent_with_catalog(env):
    # Cohérence : a_postuler + a_etudier correspondent aux offres du catalogue dont la bande
    # d'action vaut postuler / a_etudier (toutes pending, aucune tranchée ici).
    catalog = env.dispatch("GET", "/offers?candidate_id=cand-1", None, _hdr("tok-rev")).body
    actions = [i["action"] for i in catalog["items"]]
    stats = env.dispatch("GET", "/candidates/cand-1/stats", None, _hdr("tok-rev")).body
    assert stats["a_postuler"] == actions.count("postuler")
    assert stats["a_etudier"] == actions.count("a_etudier")
    assert stats["offres_total"] == catalog["total"]


def test_stats_applied_counts_and_decided_leaves_pile(env):
    # Candidature déclarée sur a : postule passe à 1, et a (tranchée) sort de « à postuler ».
    rid = decision_id("cand-1", "a")
    env.dispatch("POST", "/candidates/cand-1/offers/a/rescore", {}, _hdr("tok-rev"))
    env.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, _hdr("tok-rev"))
    env.dispatch("POST", f"/applications/{rid}/confirm", {"confirm": True}, _hdr("tok-rev"))
    env.dispatch("POST", f"/applications/{rid}/applied", {}, _hdr("tok-rev"))

    stats = env.dispatch("GET", "/candidates/cand-1/stats", None, _hdr("tok-rev")).body
    assert stats["postule"] == 1
    assert stats["a_postuler"] == 0  # a est tranchée (approved)
    assert stats["a_etudier"] == 1   # b reste pending


def test_stats_owner_gated_returns_404_out_of_scope(env):
    # str est reviewer mais ne possède pas cand-1 : 404 (anti-énumération, pas 403 distinctif).
    resp = env.dispatch("GET", "/candidates/cand-1/stats", None, _hdr("tok-str"))
    assert resp.status == 404


def test_stats_requires_token(env):
    # Régression transport : GET sans jeton → 401.
    resp = env.dispatch("GET", "/candidates/cand-1/stats", None, {})
    assert resp.status == 401


def test_stats_unknown_candidate_is_404(env):
    # cand-2 est dans le périmètre de tok-str mais n'a aucun profil : candidat inconnu → 404.
    resp = env.dispatch("GET", "/candidates/cand-2/stats", None, _hdr("tok-str"))
    assert resp.status == 404
