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
from app.auth import REVIEWER, LocalAuthProvider, User
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




def _start(api, body=None, headers=None):
    """POST /collect → renvoie (réponse, job_id) ; le spawn synchrone laisse le job terminé."""
    resp = api.dispatch("POST", "/collect", body or {}, headers)
    return resp, resp.body.get("job_id")


def test_post_collect_returns_202_with_job_id():
    resp, job_id = _start(_api(lambda **k: _report()))
    assert resp.status == 202
    assert isinstance(job_id, str) and job_id


def test_poll_done_job_serializes_report():
    def runner(*, what, where, max_offers, on_progress, should_cancel):
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
    def runner(*, what, where, max_offers, on_progress, should_cancel):
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
    def runner(*, what, where, max_offers, on_progress, should_cancel):
        return _report(collected=4, stored=4, duplicates=0, enriched=2, enriched_recovered=1)

    api = _api(runner)
    _, job_id = _start(api)
    report = api.dispatch("GET", f"/collect/{job_id}", None, None).body["report"]
    assert report["enriched"] == 2
    assert report["enriched_recovered"] == 1


def test_start_passes_criteria_and_default_max():
    captured = {}

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        captured.update(what=what, where=where, max_offers=max_offers)
        return _report()

    _start(_api(runner), {"what": "python", "where": "Paris"})
    assert captured == {"what": "python", "where": "Paris", "max_offers": _COLLECT_MAX_DEFAULT}


def test_start_defaults_empty_criteria():
    captured = {}

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        captured.update(what=what, where=where)
        return _report()

    _start(_api(runner), {})
    assert captured == {"what": "", "where": ""}


def test_start_strips_criteria():
    captured = {}

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        captured.update(what=what, where=where)
        return _report()

    _start(_api(runner), {"what": "  data  ", "where": " Lyon "})
    assert captured == {"what": "data", "where": "Lyon"}


def test_start_clamps_max_to_cap():
    captured = {}

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        captured["max_offers"] = max_offers
        return _report()

    _start(_api(runner), {"max": 10_000})
    assert captured["max_offers"] == _COLLECT_MAX_CAP


def test_start_honours_explicit_max_below_cap():
    captured = {}

    def runner(*, what, where, max_offers, on_progress, should_cancel):
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
    def runner(*, what, where, max_offers, on_progress, should_cancel):
        return _report(collected=0, stored=0, duplicates=0, source_error="AdzunaAuthError: …")

    api = _api(runner)
    _, job_id = _start(api)
    body = api.dispatch("GET", f"/collect/{job_id}", None, None).body
    assert body["status"] == "done"
    assert body["report"]["source_error"] == "AdzunaAuthError: …"


def test_runner_exception_marks_job_failed():
    def runner(*, what, where, max_offers, on_progress, should_cancel):
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

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        return _report(collected=4, stored=1, duplicates=1, failures=failures)

    api = _api(runner)
    _, job_id = _start(api)
    report = api.dispatch("GET", f"/collect/{job_id}", None, None).body["report"]
    assert report["failures"] == 2


def test_second_collect_while_running_returns_409():
    # Unicité de l'écrivain : un vrai thread bloque le runner sur un Event le temps du test.
    release = threading.Event()
    started = threading.Event()

    def runner(*, what, where, max_offers, on_progress, should_cancel):
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


def test_cancel_running_job_returns_202_then_job_cancelled():
    # Arrêt coopératif (OPP-209) : POST /collect/{id}/cancel → 202, puis le job passe cancelled.
    release = threading.Event()
    started = threading.Event()

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        started.set()
        while not should_cancel():
            if release.wait(0.01):
                break
        # Comme un vrai runner : ``cancelled`` reflète que la passe a été tronquée par le flag.
        return _report(cancelled=should_cancel())

    api = _api(runner, spawn=lambda t: threading.Thread(target=t, daemon=True).start())
    try:
        job_id = api.dispatch("POST", "/collect", {}, None).body["job_id"]
        assert started.wait(timeout=5)
        cancel = api.dispatch("POST", f"/collect/{job_id}/cancel", {}, None)
        assert cancel.status == 202
        for _ in range(500):
            body = api.dispatch("GET", f"/collect/{job_id}", None, None).body
            if body["status"] == "cancelled":
                break
            time.sleep(0.01)
        else:
            pytest.fail("le job n'est pas passé cancelled")
    finally:
        release.set()


def test_cancel_unknown_job_is_404():
    api = _api(lambda **k: _report())
    assert api.dispatch("POST", "/collect/inconnu/cancel", {}, None).status == 404


def test_serialize_job_exposes_cancel_requested():
    # Le sondage expose le drapeau d'arrêt demandé (OPP-209) — ici faux (passe nominale).
    api = _api(lambda **k: _report())
    job_id = api.dispatch("POST", "/collect", {}, None).body["job_id"]
    body = api.dispatch("GET", f"/collect/{job_id}", None, None).body
    assert body["cancel_requested"] is False


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
    # GET /collect est désormais le suivi global (OPP-208) ; une méthode d'écriture autre
    # que POST reste non supportée.
    assert _api(lambda **k: _report()).dispatch("PUT", "/collect", None, None).status == 405


def test_get_active_collect_none_when_idle():
    # Aucune collecte lancée → suivi global vide (OPP-208).
    resp = _api(lambda **k: _report()).dispatch("GET", "/collect", None, None)
    assert resp.status == 200
    assert resp.body == {"job": None}


def test_get_active_collect_reflects_running_job():
    # Un job maintenu « running » par un Event est visible via le suivi global, sans job_id.
    release = threading.Event()
    started = threading.Event()

    def runner(*, what, where, max_offers, on_progress, should_cancel):
        started.set()
        release.wait(timeout=5)
        return _report()

    api = _api(runner, spawn=lambda t: threading.Thread(target=t, daemon=True).start())
    try:
        start = api.dispatch("POST", "/collect", {}, None)
        assert start.status == 202
        assert started.wait(timeout=5)
        active = api.dispatch("GET", "/collect", None, None)
        assert active.status == 200
        assert active.body["job"] is not None
        assert active.body["job"]["job_id"] == start.body["job_id"]
        assert active.body["job"]["status"] == "running"
    finally:
        release.set()
    # Une fois terminé, le job n'est plus « actif » : le suivi global redevient vide.
    for _ in range(200):
        if api.dispatch("GET", "/collect", None, None).body["job"] is None:
            break
        time.sleep(0.01)
    else:
        pytest.fail("le job est resté « actif » après sa fin")


def test_collect_requires_reviewer_role():
    # Sans le rôle reviewer : POST et sondage refusés (403), avant toute création/lecture de job.
    viewer = _api(
        lambda **k: _report(),
        auth=LocalAuthProvider(User("moi", "viewer", frozenset({"cand-1"}))),
    )
    assert viewer.dispatch("POST", "/collect", {}).status == 403
    assert viewer.dispatch("GET", "/collect/n-importe", None).status == 403
    assert viewer.dispatch("GET", "/collect", None).status == 403  # suivi global aussi réservé
    assert viewer.dispatch("POST", "/collect/x/cancel", {}).status == 403  # annulation réservée
    # Avec le rôle : la passe démarre (202) et le sondage répond (200).
    reviewer = _api(
        lambda **k: _report(),
        auth=LocalAuthProvider(User("moi", REVIEWER, frozenset({"cand-1"}))),
    )
    resp = reviewer.dispatch("POST", "/collect", {})
    assert resp.status == 202
    job_id = resp.body["job_id"]
    assert reviewer.dispatch("GET", f"/collect/{job_id}", None).status == 200
