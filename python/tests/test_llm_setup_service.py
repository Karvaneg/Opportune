"""Tests du service de mise en route du LLM local (OPP-193)."""

from app.host_memory import OK, UNKNOWN
from app.llm_setup_service import DONE, FAILED, RUNNING, LLMSetupService
from app.ollama_provision import OllamaUnreachable, PullProgress

_GB = 1024**3

# Spawn synchrone : exécute le travail de fond immédiatement, pour des tests déterministes.
_SYNC_SPAWN = lambda target: target()  # noqa: E731


def _service(**overrides) -> LLMSetupService:
    """Service avec dépendances inoffensives par défaut (surchargées au cas par cas)."""
    defaults = dict(
        present=lambda model, host=None: False,
        pull=lambda model, host=None, on_progress=None: PullProgress("success", 1.0, done=True),
        total_memory=lambda: 16 * _GB,
        spawn=_SYNC_SPAWN,
    )
    defaults.update(overrides)
    return LLMSetupService(**defaults)


def test_status_reports_reachable_present_and_memory():
    service = _service(present=lambda model, host=None: True, total_memory=lambda: 16 * _GB)

    status = service.status()

    assert status["ollama_reachable"] is True
    assert status["model_present"] is True
    assert status["memory"]["level"] == OK


def test_status_marks_unreachable_when_ollama_down():
    def refuse(model, host=None):
        raise OllamaUnreachable("refus")

    status = _service(present=refuse).status()

    assert status["ollama_reachable"] is False
    assert status["model_present"] is False


def test_status_memory_unknown_when_unreadable():
    status = _service(total_memory=lambda: None).status()

    assert status["memory"]["level"] == UNKNOWN


def test_start_short_circuits_when_model_present():
    pulled = []
    service = _service(
        present=lambda model, host=None: True,
        pull=lambda **k: pulled.append(1) or PullProgress("success", 1.0, done=True),
    )

    snapshot = service.start()

    assert snapshot.state == DONE
    assert pulled == []  # pas de téléchargement : modèle déjà là


def test_start_runs_pull_to_done():
    def pull(model, host=None, on_progress=None):
        on_progress(PullProgress("pulling", 0.5))
        return PullProgress("success", 1.0, done=True)

    service = _service(present=lambda model, host=None: False, pull=pull)

    snapshot = service.start()

    assert snapshot.state == DONE
    assert service.progress().fraction == 1.0


def test_start_marks_failed_on_unexpected_present_error():
    # L'état est posé à RUNNING sous le verrou avant le check de présence : si ce check lève une
    # exception inattendue (pas OllamaUnreachable), start() doit résoudre en FAILED, jamais laisser
    # l'état figé sur RUNNING (sinon les start() suivants renoncent et la porte reste bloquée).
    def explode(model, host=None):
        raise RuntimeError("corps non-JSON")

    service = _service(present=explode)

    snapshot = service.start()

    assert snapshot.state == FAILED
    assert service.progress().state == FAILED


def test_start_marks_failed_on_pull_error():
    service = _service(
        present=lambda model, host=None: False,
        pull=lambda model, host=None, on_progress=None: PullProgress(
            "erreur", 0.3, error="disque plein"
        ),
    )

    snapshot = service.start()

    assert snapshot.state == FAILED
    assert snapshot.error == "disque plein"


def test_start_failed_when_ollama_unreachable():
    def refuse(model, host=None):
        raise OllamaUnreachable("refus")

    snapshot = _service(present=refuse).start()

    assert snapshot.state == FAILED


def test_start_is_idempotent_while_running():
    # Spawn qui ne lance rien : le job reste « running », un 2e start ne doit pas le relancer.
    calls = []
    service = _service(
        present=lambda model, host=None: False,
        pull=lambda **k: calls.append(1) or PullProgress("success", 1.0, done=True),
        spawn=lambda target: None,
    )

    first = service.start()
    second = service.start()

    assert first.state == RUNNING
    assert second.state == RUNNING
    assert calls == []  # le pull n'a jamais été exécuté (spawn neutralisé), ni relancé


def test_download_is_recorded_when_service_pulls_the_model():
    downloaded_models = []
    service = _service(model="ministral-3:3b", on_downloaded=downloaded_models.append)

    service.start()

    assert downloaded_models == ["ministral-3:3b"]


def test_download_is_not_recorded_when_model_was_already_present():
    downloaded_models = []
    service = _service(
        present=lambda model, host=None: True,
        on_downloaded=downloaded_models.append,
    )

    service.start()

    assert downloaded_models == []


def test_download_is_not_recorded_when_pull_fails():
    downloaded_models = []
    service = _service(
        pull=lambda model, host=None, on_progress=None: PullProgress("erreur", 0.2, error="réseau coupé"),
        on_downloaded=downloaded_models.append,
    )

    snapshot = service.start()

    assert snapshot.state == FAILED
    assert downloaded_models == []


def test_setup_succeeds_even_when_recording_the_download_fails():
    def refuse_to_write(model):
        raise OSError("disque plein")

    service = _service(on_downloaded=refuse_to_write)

    snapshot = service.start()

    assert snapshot.state == DONE


def test_setup_succeeds_even_when_recording_the_download_raises_any_error():
    def fail_unexpectedly(model):
        raise TypeError("valeur non sérialisable")

    service = _service(on_downloaded=fail_unexpectedly)

    snapshot = service.start()

    assert snapshot.state == DONE
