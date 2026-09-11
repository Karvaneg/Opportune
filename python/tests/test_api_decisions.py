"""Tests des endpoints de consultation et de décision humaine (OPP-094).

On teste ``HermesApi.dispatch`` directement (aucun réseau) avec de vrais dépôts SQLite en
mémoire. Un POST /recommendations préalable crée l'exécution et les décisions ``pending``
sur lesquelles portent GET /runs, GET /recommendations et POST .../decision.
"""

import itertools

import pytest

from api.app import HermesApi
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
    runs = RunStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    clock = (f"2026-09-04T00:00:0{n}+00:00" for n in itertools.count(0))
    run_ids = (f"run-{n}" for n in itertools.count(1))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(decisions, now=lambda: next(clock)),
        runs=runs,
        run_id=lambda: next(run_ids),
        now=lambda: "2026-09-04T12:00:00+00:00",
    )
    api = HermesApi(orchestrator)
    offers.save(_offer(id="off-app", title="App", company="Acme", url="http://app"))
    # Crée l'exécution "run-1" et la décision pending de off-app.
    api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    yield api
    conn.close()


_RID = decision_id("cand-1", "off-app")


def test_get_run_returns_execution(env):
    resp = env.dispatch("GET", "/runs/run-1", None)
    assert resp.status == 200
    assert resp.body["run_id"] == "run-1"
    assert resp.body["candidate_id"] == "cand-1"
    assert resp.body["executed_at"] == "2026-09-04T12:00:00+00:00"
    assert len(resp.body["evaluations"]) == 1
    ev = resp.body["evaluations"][0]
    assert ev["offer_id"] == "off-app"
    assert ev["score"] == 100
    assert ev["decision_status"] == "pending"  # photo au run-time
    assert ev["advisory_status"] == "approved"
    assert ev["action"] == "postuler"
    assert ev["title"] == "App"
    assert ev["company"] == "Acme"
    assert "Score 100/100" in ev["justification"]
    assert resp.body["errors"] == []


def test_get_unknown_run_returns_404(env):
    resp = env.dispatch("GET", "/runs/run-999", None)
    assert resp.status == 404
    assert "run inconnu" in resp.body["error"]


def test_delete_run_removes_it(env):
    # OPP-144 : supprimer un run le retire (GET 200 → DELETE 200 → GET 404).
    assert env.dispatch("GET", "/runs/run-1", None).status == 200
    resp = env.dispatch("DELETE", "/runs/run-1", None)
    assert resp.status == 200
    assert resp.body == {"deleted": "run-1"}
    assert env.dispatch("GET", "/runs/run-1", None).status == 404


def test_delete_run_is_idempotent(env):
    # Re-supprimer un run déjà retiré → 404 neutre (rien à retirer).
    assert env.dispatch("DELETE", "/runs/run-1", None).status == 200
    assert env.dispatch("DELETE", "/runs/run-1", None).status == 404


def test_get_recommendation_returns_decision(env):
    resp = env.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp.status == 200
    assert resp.body["recommendation_id"] == _RID
    assert resp.body["offer_id"] == "off-app"
    assert resp.body["status"] == "pending"
    assert resp.body["action"] == "postuler"
    assert resp.body["score"] == 100
    # OPP-112 : le détail porte désormais title/company, résolus depuis l'offre d'origine.
    assert resp.body["title"] == "App"
    assert resp.body["company"] == "Acme"
    assert [ev["status"] for ev in resp.body["history"]] == ["pending"]


def test_get_recommendation_title_company_fallback_when_offer_gone(env):
    # OPP-112 : offre disparue → title/company None (le front retombe sur offer_id),
    # sans régression sur le reste de la réponse.
    resp_before = env.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp_before.body["title"] == "App"

    # Supprime l'offre via l'orchestrateur (même store que l'API).
    env.orchestrator.recommendations.offers.conn.execute(
        "DELETE FROM offers WHERE id = ?", ("off-app",)
    )
    env.orchestrator.recommendations.offers.conn.commit()

    resp = env.dispatch("GET", f"/recommendations/{_RID}", None)
    assert resp.status == 200
    assert resp.body["title"] is None
    assert resp.body["company"] is None
    assert resp.body["offer_id"] == "off-app"  # fallback possible côté front


def test_get_unknown_recommendation_returns_404(env):
    resp = env.dispatch("GET", "/recommendations/cand-1:absente", None)
    assert resp.status == 404
    assert "recommandation inconnue" in resp.body["error"]


def test_post_decision_approve_persists_and_historizes(env):
    resp = env.dispatch(
        "POST", f"/recommendations/{_RID}/decision",
        {"decision": "approve", "comment": "Bonne adéquation"},
    )
    assert resp.status == 200
    assert resp.body["status"] == "approved"
    assert resp.body["comment"] == "Bonne adéquation"
    assert resp.body["title"] == "App"  # OPP-112 : enrichi aussi sur la réponse POST
    assert [ev["status"] for ev in resp.body["history"]] == ["pending", "approved"]
    # Persistance vérifiée via une relecture.
    again = env.dispatch("GET", f"/recommendations/{_RID}", None)
    assert again.body["status"] == "approved"


@pytest.mark.parametrize("verb,expected", [
    ("approve", "approved"), ("reject", "rejected"), ("defer", "deferred"),
])
def test_post_decision_maps_all_verbs(env, verb, expected):
    resp = env.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": verb})
    assert resp.status == 200
    assert resp.body["status"] == expected


def test_post_decision_invalid_verb_returns_400(env):
    resp = env.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": "maybe"})
    assert resp.status == 400
    assert "decision" in resp.body["error"]


@pytest.mark.parametrize("bad", [["approve"], {"verb": "approve"}, 1, True])
def test_post_decision_non_string_verb_returns_400(env, bad):
    # Une valeur non-hashable (list/dict) ferait lever ``dict.get`` : elle doit être
    # rejetée proprement en 400, pas remonter en 500.
    resp = env.dispatch("POST", f"/recommendations/{_RID}/decision", {"decision": bad})
    assert resp.status == 400
    assert "decision" in resp.body["error"]


def test_post_decision_unknown_recommendation_returns_404(env):
    resp = env.dispatch(
        "POST", "/recommendations/cand-1:absente/decision", {"decision": "approve"}
    )
    assert resp.status == 404
    assert "recommandation inconnue" in resp.body["error"]


def test_post_decision_non_string_comment_returns_400(env):
    resp = env.dispatch(
        "POST", f"/recommendations/{_RID}/decision",
        {"decision": "approve", "comment": 123},
    )
    assert resp.status == 400
    assert "comment" in resp.body["error"]


def test_wrong_methods_return_405(env):
    assert env.dispatch("POST", "/runs/run-1", {}).status == 405
    assert env.dispatch("POST", f"/recommendations/{_RID}", {}).status == 405
    assert env.dispatch("GET", f"/recommendations/{_RID}/decision", None).status == 405
