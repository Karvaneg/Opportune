"""Tests des filtres et de la pagination de l'API Hermes (OPP-095).

Couvre, sur ``HermesApi.dispatch`` (aucun réseau, vrais dépôts SQLite en mémoire) :

- ``POST /candidates/{id}/recommendations`` avec ``filters`` (``contract_type`` exact,
  ``skills`` en sémantique ALL) appliqués **avant** la coupe ``limit`` — seules les offres
  retenues sont évaluées/persistées ;
- ``GET /runs/{run_id}/recommendations`` paginé (``page`` / ``page_size``) et filtrable par
  ``advisory_status`` (pré-éval figée) et ``decision_status`` (état humain **courant**,
  relu en direct — fallback sur le snapshot si la décision n'est pas persistée).
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
from hermes.models import HermesRun, OfferEvaluation
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
    run_ids = (f"run-{n}" for n in itertools.count(1))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(decisions, now=lambda: "2026-09-04T00:00:00+00:00"),
        runs=runs,
        run_id=lambda: next(run_ids),
        now=lambda: "2026-09-04T12:00:00+00:00",
    )
    yield HermesApi(orchestrator), offers, decisions, runs, orchestrator
    conn.close()


def _post(api, **body):
    return api.dispatch("POST", "/candidates/cand-1/recommendations", body)


def _get_run_recos(api, run_id="run-1", query=""):
    return api.dispatch("GET", f"/runs/{run_id}/recommendations{query}", None)


# --- Filtres du POST ---------------------------------------------------------

def test_filter_contract_type_exact(env):
    api, offers, decisions, _, _ = env
    offers.save(_offer(id="cdi-1", contract_type="CDI"))
    offers.save(_offer(id="free-1", contract_type="Freelance"))

    resp = _post(api, limit=10, filters={"contract_type": "freelance"})  # normalisé → Freelance

    assert resp.status == 200
    assert [i["offer_id"] for i in resp.body["items"]] == ["free-1"]
    assert resp.body["total"] == 1
    # Seule l'offre retenue est persistée (le filtre s'applique avant limit/évaluation).
    assert decisions.count() == 1


def test_filter_skills_all_semantics(env):
    api, offers, _, _, _ = env
    offers.save(_offer(id="both", skills=["Python", "SQL"]))
    offers.save(_offer(id="py-only", skills=["Python"]))
    offers.save(_offer(id="none", skills=["Cobol"]))

    resp = _post(api, limit=10, filters={"skills": ["python", "sql"]})

    # ALL : seule l'offre listant Python ET SQL est retenue (insensible à la casse).
    assert [i["offer_id"] for i in resp.body["items"]] == ["both"]
    assert resp.body["total"] == 1


def test_filter_contract_and_skills_combined(env):
    api, offers, _, _, _ = env
    offers.save(_offer(id="ok", contract_type="Freelance", skills=["Python", "SQL"]))
    offers.save(_offer(id="wrong-contract", contract_type="CDI", skills=["Python", "SQL"]))
    offers.save(_offer(id="missing-skill", contract_type="Freelance", skills=["Python"]))

    resp = _post(api, limit=10, filters={"contract_type": "Freelance", "skills": ["Python", "SQL"]})

    assert [i["offer_id"] for i in resp.body["items"]] == ["ok"]


def test_no_filters_evaluates_all(env):
    """Rétrocompat : ``filters`` absent → aucun filtrage."""
    api, offers, _, _, _ = env
    offers.save(_offer(id="a"))
    offers.save(_offer(id="b", contract_type="Freelance"))

    resp = _post(api, limit=10)

    assert resp.body["total"] == 2
    assert {i["offer_id"] for i in resp.body["items"]} == {"a", "b"}


def test_empty_filters_evaluates_all(env):
    api, offers, _, _, _ = env
    offers.save(_offer(id="a"))
    offers.save(_offer(id="b", contract_type="Freelance"))

    resp = _post(api, limit=10, filters={"skills": [], "contract_type": None})

    assert resp.body["total"] == 2


def test_filter_skills_not_a_list_returns_400(env):
    api, offers, _, runs, _ = env
    offers.save(_offer(id="a"))
    resp = _post(api, limit=10, filters={"skills": "python"})
    assert resp.status == 400
    assert "skills" in resp.body["error"]
    assert runs.count() == 0


def test_filter_contract_type_not_string_returns_400(env):
    api, offers, _, runs, _ = env
    offers.save(_offer(id="a"))
    resp = _post(api, limit=10, filters={"contract_type": ["CDI"]})
    assert resp.status == 400
    assert "contract_type" in resp.body["error"]
    assert runs.count() == 0


# --- Pagination du GET /runs/{id}/recommendations ----------------------------

def _seed_five_matching(offers):
    for n in range(1, 6):
        offers.save(_offer(id=f"off-{n}", title=f"Offre {n}"))  # tous score 100 → approved


def test_pagination_first_and_second_page(env):
    api, offers, _, _, _ = env
    _seed_five_matching(offers)
    _post(api, limit=10)

    page1 = _get_run_recos(api, query="?page=1&page_size=2")
    assert page1.status == 200
    assert page1.body["total"] == 5
    assert page1.body["page"] == 1
    assert page1.body["page_size"] == 2
    assert page1.body["total_pages"] == 3
    assert len(page1.body["items"]) == 2

    page3 = _get_run_recos(api, query="?page=3&page_size=2")
    assert len(page3.body["items"]) == 1  # 5 = 2 + 2 + 1

    # L'union des pages couvre exactement les 5 offres, sans doublon.
    seen = [i["offer_id"] for i in page1.body["items"]]
    seen += [i["offer_id"] for i in _get_run_recos(api, query="?page=2&page_size=2").body["items"]]
    seen += [i["offer_id"] for i in page3.body["items"]]
    assert sorted(seen) == [f"off-{n}" for n in range(1, 6)]


def test_pagination_defaults(env):
    api, offers, _, _, _ = env
    _seed_five_matching(offers)
    _post(api, limit=10)
    resp = _get_run_recos(api)  # ni page ni page_size
    assert resp.body["page"] == 1
    assert resp.body["page_size"] == 20
    assert len(resp.body["items"]) == 5


def test_page_out_of_range_returns_empty_page(env):
    api, offers, _, _, _ = env
    _seed_five_matching(offers)
    _post(api, limit=10)
    resp = _get_run_recos(api, query="?page=99&page_size=2")
    assert resp.status == 200
    assert resp.body["items"] == []
    assert resp.body["total"] == 5  # total inchangé, seule la page est vide


def test_total_pages_zero_when_no_match(env):
    api, offers, _, _, _ = env
    _seed_five_matching(offers)
    _post(api, limit=10)
    resp = _get_run_recos(api, query="?advisory_status=rejected")  # aucune offre rejetée
    assert resp.body["total"] == 0
    assert resp.body["total_pages"] == 0
    assert resp.body["items"] == []


@pytest.mark.parametrize("query", ["?page=0", "?page=-1", "?page_size=0", "?page_size=101", "?page=abc"])
def test_invalid_pagination_params_return_400(env, query):
    api, offers, _, _, _ = env
    _seed_five_matching(offers)
    _post(api, limit=10)
    resp = _get_run_recos(api, query=query)
    assert resp.status == 400


def test_unknown_run_returns_404(env):
    api, _, _, _, _ = env
    resp = _get_run_recos(api, run_id="nope")
    assert resp.status == 404
    assert "run inconnu" in resp.body["error"]


# --- Filtres advisory_status / decision_status (deux registres distincts) -----

def _seed_one_per_bucket(offers):
    offers.save(_offer(id="off-app", title="App"))  # 100 → approved
    offers.save(_offer(id="off-pend", title="Pend", skills=["Python", "Java"], location="Lyon"))  # 68 → pending
    offers.save(_offer(id="off-rej", title="Rej", skills=["Cobol"], contract_type="Freelance",
                       location="Lyon", seniority="Lead"))  # 0 → rejected


def test_filter_by_advisory_status(env):
    api, offers, _, _, _ = env
    _seed_one_per_bucket(offers)
    _post(api, limit=10)
    resp = _get_run_recos(api, query="?advisory_status=approved")
    assert [i["offer_id"] for i in resp.body["items"]] == ["off-app"]
    assert resp.body["total"] == 1  # total = résultat filtré, pas les 3 du run


def test_invalid_status_filters_return_400(env):
    api, offers, _, _, _ = env
    _seed_one_per_bucket(offers)
    _post(api, limit=10)
    assert _get_run_recos(api, query="?advisory_status=bogus").status == 400
    assert _get_run_recos(api, query="?decision_status=bogus").status == 400


def test_human_decision_is_reflected_live_at_get(env):
    api, offers, _, _, _ = env
    _seed_one_per_bucket(offers)
    _post(api, limit=10)

    # État initial : off-app est advisory=approved mais decision=pending.
    before = _get_run_recos(api, query="?decision_status=pending")
    assert "off-app" in [i["offer_id"] for i in before.body["items"]]

    # Un humain approuve off-app.
    rid = decision_id("cand-1", "off-app")
    api.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"})

    # Le GET reflète immédiatement le statut courant (relu dans le DecisionStore).
    approved = _get_run_recos(api, query="?decision_status=approved")
    ids_approved = [i["offer_id"] for i in approved.body["items"]]
    assert ids_approved == ["off-app"]
    assert approved.body["items"][0]["decision_status"] == "approved"
    # ... et le filtre pending ne le retient plus (filtrage sur le statut rafraîchi).
    still_pending = _get_run_recos(api, query="?decision_status=pending")
    assert "off-app" not in [i["offer_id"] for i in still_pending.body["items"]]
    # L'advisory_status, lui, reste figé.
    assert approved.body["items"][0]["advisory_status"] == "approved"


def test_decision_status_falls_back_to_snapshot_when_absent(env):
    """Une décision absente du store retombe sur la valeur figée du snapshot."""
    api, _, _, runs, _ = env
    # Run fabriqué à la main : une offre « fantôme » sans décision persistée, dont le
    # snapshot fige decision_status="approved".
    runs.save(HermesRun(
        run_id="run-ghost",
        candidate_id="cand-1",
        executed_at="2026-09-04T12:00:00+00:00",
        evaluations=(
            OfferEvaluation(
                offer_id="ghost", score=50, decision_status="approved",
                advisory_status="pending", action="a_etudier",
                title="Ghost", company="Nowhere", justification="—",
            ),
        ),
    ))
    resp = _get_run_recos(api, run_id="run-ghost")
    assert resp.body["items"][0]["decision_status"] == "approved"  # fallback snapshot
