"""Tests des endpoints de collecte asynchrone (POST /collect + GET /collect/{id}, OPP-170).

Le registre de jobs est réel mais son **runner** est injecté (faux) et son **spawn** est
synchrone par défaut : aucun réseau, aucun Adzuna, aucun Ollama, et le job se termine dans
l'appel à ``start`` — on vérifie le contrat HTTP (202 + ``job_id`` au démarrage, sondage du
statut/bilan, plafond de ``max``, validation des critères, garde reviewer, route optionnelle,
unicité 409, et issue ``failed``). L'unicité utilise un vrai thread piloté par un ``Event``.
"""

import threading
import time

import pytest

from api.app import _COLLECT_MAX_CAP, _COLLECT_MAX_DEFAULT, HermesApi
from app.auth import REVIEWER, AuthProvider, User
from app.collection_jobs import CollectionJobRegistry
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_collection import CollectionFailure, CollectionProgress, CollectionReport
from app.offer_source import RawOffer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _report(**overrides) -> CollectionReport:
    data = dict(collected=3, stored=2, duplicates=1, failures=(), source_error=None)
    data.update(overrides)
    return CollectionReport(**data)


def _sync_spawn(target):
    """Exécute le job dans le fil de ``start`` : le job est terminé quand ``start`` rend la main."""
    target()


def _api(runner, *, auth=None, spawn=_sync_spawn) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    registry = CollectionJobRegistry(runner, spawn=spawn)
    return HermesApi(orchestrator, auth=auth, collections=registry)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _start(api, body=None, headers=None):
    """POST /collect → renvoie (réponse, job_id) ; le spawn synchrone laisse le job terminé."""
    resp = api.dispatch("POST", "/collect", body or {}, headers)
    return resp, resp.body.get("job_id")


def test_post_collect_returns_202_with_job_id():
    resp, job_id = _start(_api(lambda **k: _report()))
    assert resp.status == 202
    assert isinstance(job_id, str) and job_id


def test_poll_done_job_serializes_report():
    def runner(*, what, where, max_offers, on_progress):
        return _report(collected=5, stored=3, duplicates=2)

    api = _api(runner)
    _, job_id = _start(api, {"what": "python", "where": "Paris"})
    resp = api.dispatch("GET", f"/collect/{job_id}", None, None)
    assert resp.status == 200
    assert resp.body["status"] == "done"
    assert resp.body["error"] is None
    assert resp.body["report"] == {
        "collected": 5,
        "stored": 3,
        "duplicates": 2,
        "failures": 0,
        "source_error": None,
        "enriched": 0,
        "enriched_recovered": 0,
    }


def test_poll_reports_progress_snapshot():
    # L'avancement publié par le runner via ``on_progress`` est lisible dans l'état du job.
    def runner(*, what, where, max_offers, on_progress):
        on_progress(
            CollectionProgress(
                collected=4, stored=1, duplicates=2, failures=1, enriched=0, enriched_recovered=0
            )
        )
        return _report(collected=4, stored=1, duplicates=2)

    api = _api(runner)
    _, job_id = _start(api)
    body = api.dispatch("GET", f"/collect/{job_id}", None, None).body
    assert body["progress"] == {
        "collected": 4,
        "stored": 1,
        "duplicates": 2,
        "failures": 1,
        "enriched": 0,
        "enriched_recovered": 0,
    }


def test_poll_serializes_enrichment_counts():
    # OPP-169 : les compteurs d'enrichissement non nuls remontent dans le bilan du job.
    def runner(*, what, where, max_offers, on_progress):
        return _report(collected=4, stored=4, duplicates=0, enriched=2, enriched_recovered=1)

    api = _api(runner)
    _, job_id = _start(api)
    report = api.dispatch("GET", f"/collect/{job_id}", None, None).body["report"]
    assert report["enriched"] == 2
    assert report["enriched_recovered"] == 1


def test_start_passes_criteria_and_default_max():
    captured = {}

    def runner(*, what, where, max_offers, on_progress):
        captured.update(what=what, where=where, max_offers=max_offers)
        return _report()

    _start(_api(runner), {"what": "python", "where": "Paris"})
    assert captured == {"what": "python", "where": "Paris", "max_offers": _COLLECT_MAX_DEFAULT}


def test_start_defaults_empty_criteria():
    captured = {}

    def runner(*, what, where, max_offers, on_progress):
        captured.update(what=what, where=where)
        return _report()

    _start(_api(runner), {})
    assert captured == {"what": "", "where": ""}


def test_start_strips_criteria():
    captured = {}

    def runner(*, what, where, max_offers, on_progress):
        captured.update(what=what, where=where)
        return _report()

    _start(_api(runner), {"what": "  data  ", "where": " Lyon "})
    assert captured == {"what": "data", "where": "Lyon"}


def test_start_clamps_max_to_cap():
    captured = {}

    def runner(*, what, where, max_offers, on_progress):
        captured["max_offers"] = max_offers
        return _report()

    _start(_api(runner), {"max": 10_000})
    assert captured["max_offers"] == _COLLECT_MAX_CAP


def test_start_honours_explicit_max_below_cap():
    captured = {}

    def runner(*, what, where, max_offers, on_progress):
        captured["max_offers"] = max_offers
        return _report()

    _start(_api(runner), {"max": 7})
    assert captured["max_offers"] == 7


@pytest.mark.parametrize("bad", [0, -1, True, "20", 3.5])
def test_start_rejects_invalid_max(bad):
    api = _api(lambda **k: _report())
    assert api.dispatch("POST", "/collect", {"max": bad}, None).status == 400


@pytest.mark.parametrize("key", ["what", "where"])
def test_start_rejects_non_string_criteria(key):
    api = _api(lambda **k: _report())
    assert api.dispatch("POST", "/collect", {key: 123}, None).status == 400


def test_source_error_surfaces_in_done_report_not_status():
    # Panne de la source (identifiants Adzuna manquants, quota…) : le runner rend un bilan
    # porteur de ``source_error`` — le job est ``done`` (pas ``failed``) et le détail est dans
    # le bilan. Une panne de source n'est pas un échec de job.
    def runner(*, what, where, max_offers, on_progress):
        return _report(collected=0, stored=0, duplicates=0, source_error="AdzunaAuthError: …")

    api = _api(runner)
    _, job_id = _start(api)
    body = api.dispatch("GET", f"/collect/{job_id}", None, None).body
    assert body["status"] == "done"
    assert body["report"]["source_error"] == "AdzunaAuthError: …"


def test_runner_exception_marks_job_failed():
    def runner(*, what, where, max_offers, on_progress):
        raise RuntimeError("boom")

    api = _api(runner)
    _, job_id = _start(api)
    body = api.dispatch("GET", f"/collect/{job_id}", None, None).body
    assert body["status"] == "failed"
    assert body["report"] is None
    assert "boom" in body["error"]


def test_done_report_counts_failures():
    failures = (
        CollectionFailure(raw=RawOffer(source="adzuna", raw_text="x", url="u1"), error="boom"),
        CollectionFailure(raw=RawOffer(source="adzuna", raw_text="y", url="u2"), error="bam"),
    )

    def runner(*, what, where, max_offers, on_progress):
        return _report(collected=4, stored=1, duplicates=1, failures=failures)

    api = _api(runner)
    _, job_id = _start(api)
    report = api.dispatch("GET", f"/collect/{job_id}", None, None).body["report"]
    assert report["failures"] == 2


def test_second_collect_while_running_returns_409():
    # Unicité de l'écrivain : un vrai thread bloque le runner sur un Event le temps du test.
    release = threading.Event()
    started = threading.Event()

    def runner(*, what, where, max_offers, on_progress):
        started.set()
        release.wait(timeout=5)
        return _report()

    api = _api(runner, spawn=lambda t: threading.Thread(target=t, daemon=True).start())
    try:
        first = api.dispatch("POST", "/collect", {}, None)
        assert first.status == 202
        assert started.wait(timeout=5)
        # Un job tourne encore → second démarrage refusé.
        assert api.dispatch("POST", "/collect", {}, None).status == 409
    finally:
        release.set()
    # Une fois terminé, le créneau se libère : un nouveau démarrage repasse.
    for _ in range(200):
        if api.dispatch("POST", "/collect", {}, None).status == 202:
            break
        time.sleep(0.01)
    else:
        pytest.fail("le créneau de collecte ne s'est pas libéré après la fin du job")


def test_get_unknown_job_is_404():
    api = _api(lambda **k: _report())
    assert api.dispatch("GET", "/collect/does-not-exist", None, None).status == 404


def test_collect_routes_absent_without_registry():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator)  # pas de registre → routes non montées
    assert api.dispatch("POST", "/collect", {}, None).status == 404
    assert api.dispatch("GET", "/collect/x", None, None).status == 404


def test_collect_unsupported_method_405():
    assert _api(lambda **k: _report()).dispatch("GET", "/collect", None, None).status == 405


def test_collect_requires_reviewer_role():
    auth = AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-view": User("view", "viewer", frozenset({"cand-1"})),
    })
    api = _api(lambda **k: _report(), auth=auth)
    assert api.dispatch("POST", "/collect", {}, _hdr("tok-view")).status == 403
    assert api.dispatch("POST", "/collect", {}, None).status == 401
    resp = api.dispatch("POST", "/collect", {}, _hdr("tok-rev"))
    assert resp.status == 202
    # Le sondage exige aussi le rôle reviewer.
    job_id = resp.body["job_id"]
    assert api.dispatch("GET", f"/collect/{job_id}", None, _hdr("tok-view")).status == 403
    assert api.dispatch("GET", f"/collect/{job_id}", None, _hdr("tok-rev")).status == 200
