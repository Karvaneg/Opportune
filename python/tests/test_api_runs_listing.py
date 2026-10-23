"""Tests du listing paginé des runs — ``GET /runs`` (OPP-101).

Vérifie : ordre antéchronologique, filtrage par **périmètre** (l'utilisateur ne voit que
les runs de ses candidats), pagination (page/page_size/total/total_pages), forme **résumé**
(volumétrie sans les évaluations détaillées) et validation (400). Chaque scénario compose une
``HermesApi`` portant l'identité locale voulue (local-first, OPP-181). Les runs sont semés
directement via ``RunStore`` pour contrôler dates et périmètres.
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.models import HermesRun, OfferEvaluation
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

# Trois périmètres sur les mêmes runs : cand-1 seul, cand-1+cand-2, et aucun.
ONE = User("moi", REVIEWER, frozenset({"cand-1"}))
BOTH = User("moi", REVIEWER, frozenset({"cand-1", "cand-2"}))
NONE = User("moi", REVIEWER, frozenset())


def _run(run_id: str, candidate_id: str, executed_at: str, *, evals=0, errs=0) -> HermesRun:
    evaluations = tuple(OfferEvaluation(f"off-{i}", 50) for i in range(evals))
    errors = tuple(f"err-{i}" for i in range(errs))
    return HermesRun(run_id, candidate_id, executed_at, evaluations, errors)


@pytest.fixture
def api_as():
    """Fabrique d'API sur une base commune : ``api_as(user)`` porte l'identité ``user``."""
    conn = connect(":memory:")
    runs = RunStore(conn)
    # cand-1 : deux runs (01/09 et 03/09) ; cand-2 : un run (02/09).
    runs.save(_run("r-a1", "cand-1", "2026-09-01T10:00:00+00:00", evals=1))
    runs.save(_run("r-a2", "cand-1", "2026-09-03T10:00:00+00:00", evals=2, errs=1))
    runs.save(_run("r-b1", "cand-2", "2026-09-02T10:00:00+00:00", evals=0))

    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=runs,
    )

    def _make(user: User) -> HermesApi:
        return HermesApi(orchestrator, None, LocalAuthProvider(user))

    yield _make
    conn.close()


def _ids(resp) -> list[str]:
    return [item["run_id"] for item in resp.body["items"]]


# --- Périmètre + ordre --------------------------------------------------------

def test_lists_only_owned_runs_newest_first(api_as):
    resp = api_as(ONE).dispatch("GET", "/runs")
    assert resp.status == 200
    # cand-1 uniquement, plus récent d'abord.
    assert _ids(resp) == ["r-a2", "r-a1"]


def test_scope_spanning_multiple_candidates(api_as):
    resp = api_as(BOTH).dispatch("GET", "/runs")
    assert _ids(resp) == ["r-a2", "r-b1", "r-a1"]  # 03/09, 02/09, 01/09


def test_empty_scope_returns_empty_list(api_as):
    resp = api_as(NONE).dispatch("GET", "/runs")
    assert resp.status == 200
    assert resp.body["items"] == [] and resp.body["total"] == 0


# --- Filtre ?candidate_id (OPP-177) -------------------------------------------

def test_candidate_id_filter_narrows_to_one_candidate(api_as):
    # BOTH possède cand-1 ET cand-2 ; le filtre restreint le listing à cand-2 seul.
    resp = api_as(BOTH).dispatch("GET", "/runs?candidate_id=cand-2")
    assert resp.status == 200
    assert _ids(resp) == ["r-b1"]
    assert resp.body["total"] == 1  # ne compte pas les runs de cand-1


def test_candidate_id_filter_owner_gated_404(api_as):
    # ONE ne possède pas cand-2 → 404 neutre (comme /offers?candidate_id), pas de fuite.
    resp = api_as(ONE).dispatch("GET", "/runs?candidate_id=cand-2")
    assert resp.status == 404


# --- Forme résumé -------------------------------------------------------------

def test_summary_shape_has_counts_not_evaluations(api_as):
    resp = api_as(ONE).dispatch("GET", "/runs")
    top = resp.body["items"][0]  # r-a2 : 2 évaluations, 1 erreur
    assert top == {
        "run_id": "r-a2",
        "candidate_id": "cand-1",
        "executed_at": "2026-09-03T10:00:00+00:00",
        "evaluation_count": 2,
        "error_count": 1,
    }
    assert "evaluations" not in top  # listing ≠ détail (pas de payload lourd)


# --- Pagination ---------------------------------------------------------------

def test_pagination_slices_and_counts(api_as):
    api = api_as(BOTH)
    p1 = api.dispatch("GET", "/runs?page=1&page_size=2")
    assert _ids(p1) == ["r-a2", "r-b1"]
    assert (p1.body["total"], p1.body["total_pages"], p1.body["page"]) == (3, 2, 1)
    p2 = api.dispatch("GET", "/runs?page=2&page_size=2")
    assert _ids(p2) == ["r-a1"]
    assert p2.body["page"] == 2


@pytest.mark.parametrize("qs", ["page=0", "page_size=0", "page_size=101", "page=x"])
def test_invalid_pagination_is_400(api_as, qs):
    assert api_as(ONE).dispatch("GET", f"/runs?{qs}").status == 400


# --- Méthode ------------------------------------------------------------------

def test_rejects_non_get(api_as):
    assert api_as(ONE).dispatch("POST", "/runs", {}).status == 405


# --- Mode ouvert --------------------------------------------------------------

def test_open_mode_lists_all_runs():
    conn = connect(":memory:")
    runs = RunStore(conn)
    runs.save(_run("r-a1", "cand-1", "2026-09-01T10:00:00+00:00"))
    runs.save(_run("r-b1", "cand-2", "2026-09-02T10:00:00+00:00"))
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=runs,
    )
    resp = HermesApi(orchestrator).dispatch("GET", "/runs", None, None)
    assert resp.status == 200
    assert _ids(resp) == ["r-b1", "r-a1"]  # tous, newest-first
    conn.close()
