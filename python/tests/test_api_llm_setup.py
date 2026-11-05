"""Tests des endpoints de mise en route du LLM local (/system/llm/*, OPP-193).

Le service est réel mais ses dépendances Ollama/RAM sont injectées (fausses) et son spawn est
synchrone : aucun réseau, aucun Ollama. On vérifie le contrat HTTP (statut, lancement 202 du
téléchargement, sondage de l'avancement, et 404 quand le service n'est pas câblé).
"""

from api.app import HermesApi
from app.auth import LocalAuthProvider, REVIEWER, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.llm_setup_service import LLMSetupService
from app.ollama_provision import PullProgress
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

_GB = 1024**3
OWNER = User("moi", REVIEWER, frozenset({"cand-1"}))


def _api(llm_setup) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(
        orchestrator, auth=LocalAuthProvider(OWNER), llm_setup=llm_setup
    )


def _setup_service(**overrides) -> LLMSetupService:
    defaults = dict(
        present=lambda model, host=None: False,
        pull=lambda model, host=None, on_progress=None: PullProgress("success", 1.0, done=True),
        total_memory=lambda: 16 * _GB,
        spawn=lambda target: target(),
    )
    defaults.update(overrides)
    return LLMSetupService(**defaults)


def test_status_returns_availability():
    api = _api(_setup_service(present=lambda model, host=None: True))

    response = api.dispatch("GET", "/system/llm/status", {}, {})

    assert response.status == 200
    assert response.body["model_present"] is True
    assert response.body["memory"]["level"] == "ok"


def test_post_setup_starts_download_and_returns_202():
    api = _api(_setup_service(present=lambda model, host=None: False))

    response = api.dispatch("POST", "/system/llm/setup", {}, {})

    assert response.status == 202
    assert response.body["state"] == "done"  # spawn synchrone → terminé à la main rendue


def test_get_setup_polls_progress():
    api = _api(_setup_service())

    response = api.dispatch("GET", "/system/llm/setup", {}, {})

    assert response.status == 200
    assert response.body["state"] in {"idle", "running", "done", "failed"}


def test_routes_absent_without_service():
    api = _api(None)

    response = api.dispatch("GET", "/system/llm/status", {}, {})

    assert response.status == 404
