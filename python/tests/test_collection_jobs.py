"""Tests du registre de jobs de collecte asynchrone (OPP-170).

Runner injecté (faux) et spawn contrôlé : on vérifie le cycle de vie d'un job (running →
done/failed), la publication de progression, l'unicité de l'écrivain (``CollectionAlreadyRunning``
puis libération du créneau), et l'isolement d'une panne de source (rendue dans le bilan, job
``done``) d'une exception inattendue (job ``failed``).
"""

import threading
import time

import pytest

from app.collection_jobs import (
    CANCELLED,
    DONE,
    FAILED,
    RUNNING,
    _EMPTY_PROGRESS,
    _MAX_RETAINED_JOBS,
    CollectionAlreadyRunning,
    CollectionJob,
    CollectionJobRegistry,
)
from app.offer_collection import CollectionProgress, CollectionReport


def _report(**overrides) -> CollectionReport:
    data = dict(collected=2, stored=2, duplicates=0, failures=())
    data.update(overrides)
    return CollectionReport(**data)


def _sync_spawn(target):
    target()


def test_start_runs_job_and_marks_done_with_report():
    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        return _report(collected=3, stored=3)

    registry = CollectionJobRegistry(runner, spawn=_sync_spawn)
    job_id = registry.start(what="dev", where="", max_offers=5)

    job = registry.get(job_id)
    assert job is not None
    assert job.status == DONE
    assert job.report.stored == 3
    assert job.error is None


def test_start_forwards_criteria_to_runner():
    captured = {}

    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        captured.update(what=what, where=where, max_offers=max_offers)
        return _report()

    CollectionJobRegistry(runner, spawn=_sync_spawn).start(
        what="python", where="Lyon", max_offers=7
    )
    assert captured == {"what": "python", "where": "Lyon", "max_offers": 7}


def test_start_forwards_source_to_runner():
    captured = {}

    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        captured["source"] = source
        return _report()

    registry = CollectionJobRegistry(runner, spawn=_sync_spawn)

    registry.start(what="", where="", max_offers=1)
    assert captured["source"] == "adzuna"

    registry.start(what="", where="", max_offers=1, source="rss")
    assert captured["source"] == "rss"


def test_progress_callback_updates_job_snapshot():
    progress = CollectionProgress(
        collected=4, stored=2, duplicates=1, failures=1, enriched=1, enriched_recovered=1
    )

    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        on_progress(progress)
        return _report()

    registry = CollectionJobRegistry(runner, spawn=_sync_spawn)
    job_id = registry.start(what="", where="", max_offers=5)
    assert registry.get(job_id).progress == progress


def test_runner_exception_marks_job_failed():
    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        raise RuntimeError("kaboom")

    registry = CollectionJobRegistry(runner, spawn=_sync_spawn)
    job_id = registry.start(what="", where="", max_offers=5)

    job = registry.get(job_id)
    assert job.status == FAILED
    assert job.report is None
    assert "kaboom" in job.error


def test_source_error_report_keeps_job_done():
    # Une panne de source est rendue DANS le bilan ; le job reste ``done`` (pas ``failed``).
    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        return _report(collected=0, stored=0, source_error="AdzunaAuthError: nope")

    registry = CollectionJobRegistry(runner, spawn=_sync_spawn)
    job_id = registry.start(what="", where="", max_offers=5)

    job = registry.get(job_id)
    assert job.status == DONE
    assert job.report.source_error == "AdzunaAuthError: nope"


def test_cancel_marks_job_cancelled_and_sets_flag():
    # Annulation coopérative (OPP-209) : le runner tourne jusqu'à ce que should_cancel soit vrai,
    # puis le job passe ``cancelled`` en conservant son bilan partiel.
    release = threading.Event()
    started = threading.Event()

    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        started.set()
        while not should_cancel():
            if release.wait(0.01):  # garde-fou anti-blocage du test
                break
        # Comme un vrai runner : ``cancelled`` reflète que la passe a été tronquée par le flag.
        return _report(collected=1, stored=1, cancelled=should_cancel())

    registry = CollectionJobRegistry(
        runner, spawn=lambda t: threading.Thread(target=t, daemon=True).start()
    )
    job_id = registry.start(what="", where="", max_offers=5)
    try:
        assert started.wait(timeout=5)
        assert registry.cancel(job_id) is True
        assert registry.get(job_id).cancel_requested is True
        for _ in range(500):
            if registry.get(job_id).status == CANCELLED:
                break
            time.sleep(0.01)
        else:
            pytest.fail("le job ne s'est pas arrêté après cancel")
    finally:
        release.set()
    assert registry.get(job_id).report.stored == 1  # bilan partiel conservé


def test_late_cancel_keeps_job_done_when_pass_completed():
    # Course fin-de-passe (OPP-209) : le ``cancel`` est accepté pendant que le job est encore
    # ``running``, mais le runner a déjà mené la passe à terme (``report.cancelled`` faux). Le
    # job doit rester ``done`` avec son bilan complet — jamais figé à tort en ``cancelled`` —
    # même si ``cancel_requested`` reste vrai (la demande a bien eu lieu, trop tard).
    release = threading.Event()
    started = threading.Event()

    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        started.set()
        release.wait(timeout=5)  # bloque jusqu'à ce que le test ait posé le cancel
        return _report(collected=2, stored=2)  # passe menée à terme : cancelled implicitement faux

    registry = CollectionJobRegistry(
        runner, spawn=lambda t: threading.Thread(target=t, daemon=True).start()
    )
    job_id = registry.start(what="", where="", max_offers=5)
    assert started.wait(timeout=5)
    assert registry.cancel(job_id) is True  # accepté : le job est encore running
    release.set()
    for _ in range(500):
        if registry.get(job_id).status != RUNNING:
            break
        time.sleep(0.01)
    else:
        pytest.fail("le job ne s'est pas terminé")
    job = registry.get(job_id)
    assert job.status == DONE  # passe complète → done, pas cancelled
    assert job.report.stored == 2  # bilan complet conservé
    assert job.cancel_requested is True  # la demande d'arrêt a bien été enregistrée


def test_cancel_unknown_or_terminated_returns_false():
    registry = CollectionJobRegistry(lambda **k: _report(), spawn=_sync_spawn)
    assert registry.cancel("inconnu") is False
    job_id = registry.start(what="", where="", max_offers=1)  # spawn synchrone → déjà terminé
    assert registry.get(job_id).status == DONE
    assert registry.cancel(job_id) is False  # rien à annuler sur un job terminé


def test_get_unknown_job_returns_none():
    registry = CollectionJobRegistry(lambda **k: _report(), spawn=_sync_spawn)
    assert registry.get("nope") is None


def test_registry_evicts_oldest_terminated_jobs_beyond_cap():
    # Avec un spawn synchrone chaque job se termine dans ``start`` : on en enchaîne plus que la
    # capacité et on vérifie que seuls les ``_MAX_RETAINED_JOBS`` plus récents restent consultables.
    registry = CollectionJobRegistry(lambda **k: _report(), spawn=_sync_spawn)
    ids = [registry.start(what="", where="", max_offers=1) for _ in range(_MAX_RETAINED_JOBS + 3)]

    evicted, retained = ids[:3], ids[3:]
    assert all(registry.get(job_id) is None for job_id in evicted)  # les 3 plus anciens évincés
    assert all(registry.get(job_id) is not None for job_id in retained)
    assert len(retained) == _MAX_RETAINED_JOBS


def test_prune_never_evicts_the_active_job_even_if_oldest():
    # Cas limite : le job actif est le plus ancien inséré. ``_prune_locked`` doit le préserver
    # et n'évincer que des terminés, sans jamais descendre sous « uniquement l'actif ».
    registry = CollectionJobRegistry(lambda **k: _report(), spawn=_sync_spawn)
    registry._active = "active"
    registry._jobs["active"] = CollectionJob(id="active", status=RUNNING, progress=_EMPTY_PROGRESS)
    for i in range(_MAX_RETAINED_JOBS + 3):
        registry._jobs[f"done{i}"] = CollectionJob(
            id=f"done{i}", status=DONE, progress=_EMPTY_PROGRESS
        )

    registry._prune_locked()

    assert len(registry._jobs) == _MAX_RETAINED_JOBS
    assert "active" in registry._jobs  # jamais évincé malgré son ancienneté


def test_second_start_while_running_raises_then_slot_frees():
    release = threading.Event()
    started = threading.Event()

    def runner(*, source, what, where, max_offers, on_progress, should_cancel):
        started.set()
        release.wait(timeout=5)
        return _report()

    registry = CollectionJobRegistry(
        runner, spawn=lambda t: threading.Thread(target=t, daemon=True).start()
    )
    first_id = registry.start(what="", where="", max_offers=5)
    assert started.wait(timeout=5)
    assert registry.get(first_id).status == RUNNING

    with pytest.raises(CollectionAlreadyRunning):
        registry.start(what="", where="", max_offers=5)

    release.set()
    for _ in range(200):
        if registry.get(first_id).status == DONE:
            break
        time.sleep(0.01)
    else:
        pytest.fail("le premier job ne s'est jamais terminé")

    # Créneau libéré : un nouveau job démarre.
    second_id = registry.start(what="", where="", max_offers=5)
    assert second_id != first_id
