"""Service de mise en route du LLM local au 1er lancement (OPP-193).

Expose à l'API ce qu'il faut pour l'écran de premier lancement :

- :meth:`status` — Ollama est-il joignable ? le modèle est-il présent ? quelle RAM ?
- :meth:`start` — lance (une fois) le téléchargement du modèle en tâche de fond, idempotent
  et court-circuité si le modèle est déjà là (« les lancements suivants réutilisent
  l'existant ») ;
- :meth:`progress` — avancement courant du téléchargement, pour le sondage du front.

Le travail bloquant (``/api/pull``) tourne dans un **thread de fond** : l'exécuter dans le
fil HTTP gèlerait le serveur séquentiel. Les fonctions Ollama et la lecture RAM sont
**injectées**, pour tester le service sans réseau ni dépendre de la machine.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from app.host_memory import assess_memory, total_memory_bytes
from app.llm import DEFAULT_MODEL, DEFAULT_OLLAMA_HOST
from app.ollama_provision import (
    OllamaUnreachable,
    PullProgress,
    model_present,
    pull_model,
)

# États du setup. ``idle`` tant qu'aucun téléchargement n'a démarré ; ``running`` pendant le
# pull ; ``done`` dès que le modèle est prêt (téléchargé ou déjà présent) ; ``failed`` sur échec.
IDLE = "idle"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


@dataclass(frozen=True)
class SetupSnapshot:
    """Instantané de l'avancement du setup, rendu tel quel au front (sondage)."""

    state: str
    status: str
    fraction: float
    error: str | None = None


class LLMSetupService:
    """Statut et mise en route du modèle local, avec téléchargement suivi par sondage."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_OLLAMA_HOST,
        present: Callable[..., bool] = model_present,
        pull: Callable[..., PullProgress] = pull_model,
        total_memory: Callable[[], int | None] = total_memory_bytes,
        spawn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._model = model
        self._host = host
        self._present = present
        self._pull = pull
        self._total_memory = total_memory
        self._spawn = spawn or _spawn_daemon
        self._lock = threading.Lock()
        self._snapshot = SetupSnapshot(IDLE, "", 0.0)

    def status(self) -> dict:
        """État de disponibilité du LLM : Ollama joignable, modèle présent, verdict RAM."""
        try:
            present = self._present(self._model, host=self._host)
            reachable = True
        except OllamaUnreachable:
            present, reachable = False, False
        memory = assess_memory(self._total_memory())
        with self._lock:
            setup = self._snapshot
        return {
            "ollama_reachable": reachable,
            "model": self._model,
            "model_present": present,
            "memory": {
                "level": memory.level,
                "total_gb": memory.total_gb,
                "recommended_gb": memory.recommended_gb,
                "minimum_gb": memory.minimum_gb,
            },
            "setup": serialize_snapshot(setup),
        }

    def start(self) -> SetupSnapshot:
        """Lance le téléchargement du modèle en fond ; rend l'instantané courant.

        Idempotent : si un setup tourne déjà, ne relance rien. Court-circuité si le modèle est
        déjà présent (``done`` immédiat) — pas de re-téléchargement aux lancements suivants.
        """
        with self._lock:
            if self._snapshot.state == RUNNING:
                return self._snapshot

        try:
            if self._present(self._model, host=self._host):
                return self._set(SetupSnapshot(DONE, "success", 1.0))
        except OllamaUnreachable as exc:
            return self._set(SetupSnapshot(FAILED, "ollama injoignable", 0.0, error=str(exc)))

        self._set(SetupSnapshot(RUNNING, "pulling manifest", 0.0))
        self._spawn(self._run)
        # On rend l'état **courant** après le spawn : avec un spawn de fond (prod) il est encore
        # ``running`` ; avec un spawn synchrone (tests) le job est déjà terminé (``done``/``failed``).
        return self.progress()

    def progress(self) -> SetupSnapshot:
        """Instantané courant du setup (pour le sondage du front)."""
        with self._lock:
            return self._snapshot

    def _run(self) -> None:
        """Corps du thread de fond : télécharge le modèle, publie progression et issue."""
        try:
            result = self._pull(self._model, host=self._host, on_progress=self._on_progress)
        except Exception as exc:  # noqa: BLE001 — consigné dans l'instantané, jamais avalé
            self._set(SetupSnapshot(FAILED, "échec du téléchargement", self._fraction(), error=f"{type(exc).__name__}: {exc}"))
            return
        if result.error is not None:
            self._set(SetupSnapshot(FAILED, result.status, result.fraction, error=result.error))
        else:
            self._set(SetupSnapshot(DONE, result.status, 1.0))

    def _on_progress(self, progress: PullProgress) -> None:
        self._set(SetupSnapshot(RUNNING, progress.status, progress.fraction))

    def _set(self, snapshot: SetupSnapshot) -> SetupSnapshot:
        with self._lock:
            self._snapshot = snapshot
            return snapshot

    def _fraction(self) -> float:
        with self._lock:
            return self._snapshot.fraction


def serialize_snapshot(snapshot: SetupSnapshot) -> dict:
    """Sérialise un instantané de setup pour la réponse HTTP (source unique, cf. ``api.app``)."""
    return {
        "state": snapshot.state,
        "status": snapshot.status,
        "fraction": snapshot.fraction,
        "error": snapshot.error,
    }


def _spawn_daemon(target: Callable[[], None]) -> None:
    """Lance ``target`` dans un thread démon (spawn par défaut du service)."""
    threading.Thread(target=target, daemon=True).start()
