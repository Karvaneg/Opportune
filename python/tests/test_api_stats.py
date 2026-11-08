"""Tests de l'endpoint d'agrégats du cockpit (OPP-163).

``GET /candidates/{id}/stats`` : compteurs pré-calculés de l'entonnoir, candidat inconnu → 404.
Vrais dépôts SQLite en mémoire ; aucune I/O réseau. Le gating identité/rôle est couvert par
``test_api_auth.py`` (local-first, OPP-181).
"""

import itertools

import pytest

from api.app import HermesApi
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.application_tracking_service import ApplicationTrackingService
from app.application_tracking_store import ApplicationTrackingStore
from app.auth import REVIEWER, LocalAuthProvider, User
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
    tracking = ApplicationTrackingService(
        applications, ApplicationTrackingStore(conn), now=lambda: "2026-09-07T00:00:00+00:00"
    )
    # Identité locale : propriétaire reviewer de cand-1 (et cand-2, laissé sans profil pour le
    # cas « candidat inconnu »).
    auth = LocalAuthProvider(User("moi", REVIEWER, frozenset({"cand-1", "cand-2"})))
    api = HermesApi(orchestrator, actions, auth, tracking=tracking)
    yield api
    conn.close()


def test_stats_all_undecided_are_a_etudier(env):
    # Entonnoir piloté par les décisions : sans décision, les 3 offres sont « à étudier ».
    resp = env.dispatch("GET", "/candidates/cand-1/stats", None, None)
    assert resp.status == 200
    assert resp.body == {
        "a_etudier": 3, "a_postuler": 0, "postule": 0, "offres_total": 3,
        "entretiens_prevus": 0, "a_relancer": 0,
    }


def test_stats_funnel_follows_my_decisions(env):
    # Approuver a → à postuler ; approuver + candidater b → postulé ; c reste à étudier.
    for oid in ("a", "b"):
        rid = decision_id("cand-1", oid)
        env.dispatch("POST", f"/candidates/cand-1/offers/{oid}/rescore", {}, None)
        env.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)
    rid_b = decision_id("cand-1", "b")
    env.dispatch("POST", f"/applications/{rid_b}/confirm", {"confirm": True}, None)
    env.dispatch("POST", f"/applications/{rid_b}/applied", {}, None)

    stats = env.dispatch("GET", "/candidates/cand-1/stats", None, None).body
    assert stats == {
        "a_etudier": 1, "a_postuler": 1, "postule": 1, "offres_total": 3,
        "entretiens_prevus": 0, "a_relancer": 1,
    }


def test_stats_coherent_with_catalog_funnel(env):
    # Cohérence cartes ↔ catalogue : les compteurs égalent l'entonnoir dérivé de l'état
    # (décision + candidature) que le catalogue expose par offre. Approuve a pour un cas non trivial.
    rid = decision_id("cand-1", "a")
    env.dispatch("POST", "/candidates/cand-1/offers/a/rescore", {}, None)
    env.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)

    catalog = env.dispatch("GET", "/offers?candidate_id=cand-1", None, None).body
    stats = env.dispatch("GET", "/candidates/cand-1/stats", None, None).body

    def stage(i):
        if i["applied"]:
            return "postule"
        if i["decision_status"] == "approved":
            return "a_postuler"
        if i["decision_status"] in (None, "pending"):
            return "a_etudier"
        return None

    stages = [stage(i) for i in catalog["items"]]
    assert stats["a_etudier"] == stages.count("a_etudier")
    assert stats["a_postuler"] == stages.count("a_postuler")
    assert stats["postule"] == stages.count("postule")
    assert stats["offres_total"] == catalog["total"]


def test_stats_counts_upcoming_interviews(env):
    # Candidater à a, puis planifier un entretien à une date lointaine (toujours « à venir »).
    rid = decision_id("cand-1", "a")
    env.dispatch("POST", "/candidates/cand-1/offers/a/rescore", {}, None)
    env.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)
    env.dispatch("POST", f"/applications/{rid}/confirm", {"confirm": True}, None)
    env.dispatch("POST", f"/applications/{rid}/applied", {}, None)
    env.dispatch(
        "POST", f"/applications/{rid}/tracking",
        {"kind": "interview", "event_date": "2099-01-01"}, None,
    )

    stats = env.dispatch("GET", "/candidates/cand-1/stats", None, None).body

    assert stats["entretiens_prevus"] == 1


def test_stats_owned_candidate_without_profile_is_200(env):
    # Révisé (OPP-182) : cand-2 est dans le périmètre mais n'a pas encore de profil (« nouveau
    # profil »). L'entonnoir ne dépend pas du profil → 200 avec des compteurs cohérents (aucune
    # décision → tout « à étudier »), plutôt qu'un 404 qui ferait afficher un bandeau d'erreur
    # au cockpit au lieu du guide d'accueil.
    resp = env.dispatch("GET", "/candidates/cand-2/stats", None, None)
    assert resp.status == 200
    assert resp.body["a_postuler"] == 0 and resp.body["postule"] == 0
    assert resp.body["a_etudier"] == resp.body["offres_total"]


def _decide(api, offer_id, decision):
    """Score puis tranche l'offre ; rend (recommendation_id, score de la décision)."""
    rid = decision_id("cand-1", offer_id)
    api.dispatch("POST", f"/candidates/cand-1/offers/{offer_id}/rescore", {}, None)
    api.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": decision}, None)
    return rid, api.orchestrator.decisions.get(rid).score


def test_scoring_quality_compares_retained_and_rejected_scores(env):
    _, score_a = _decide(env, "a", "approve")
    rid_b, score_b = _decide(env, "b", "approve")
    env.dispatch("POST", f"/applications/{rid_b}/confirm", {"confirm": True}, None)
    env.dispatch("POST", f"/applications/{rid_b}/applied", {}, None)
    _, score_c = _decide(env, "c", "reject")

    resp = env.dispatch("GET", "/candidates/cand-1/scoring-quality", None, None)

    assert resp.status == 200
    assert resp.body["retained"]["count"] == 2
    assert resp.body["retained"]["mean"] == round((score_a + score_b) / 2, 1)
    assert resp.body["rejected"]["count"] == 1
    assert resp.body["rejected"]["mean"] == score_c
    assert resp.body["verdict"] == "insuffisant"
    assert resp.body["min_per_group"] == 10
    assert (resp.body["high_threshold"], resp.body["medium_threshold"]) == (80, 60)
    assert resp.body["gap"] == round((score_a + score_b) / 2 - score_c, 1)


def test_scoring_quality_without_decisions_is_insufficient(env):
    candidate_path = "/candidates/cand-2/scoring-quality"

    resp = env.dispatch("GET", candidate_path, None, None)

    assert resp.status == 200
    assert resp.body["retained"] == {
        "count": 0, "mean": None, "bands": {"high": 0, "medium": 0, "low": 0},
    }
    assert resp.body["verdict"] == "insuffisant"


def test_scoring_quality_outside_scope_is_404(env):
    candidate_path = "/candidates/inconnu/scoring-quality"

    resp = env.dispatch("GET", candidate_path, None, None)

    assert resp.status == 404
