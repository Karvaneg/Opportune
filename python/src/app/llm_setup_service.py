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
        on_downloaded: Callable[[str], None] | None = None,
    ) -> None:
        self._model = model
        self._host = host
        self._present = present
        self._pull = pull
        self._total_memory = total_memory
        self._spawn = spawn or _spawn_daemon
        # Appelé avec le nom du modèle quand **ce service** vient de le télécharger (OPP-251).
        # Jamais appelé quand le modèle était déjà présent : c'est ce qui permet de distinguer
        # un modèle apporté par Opportune d'un modèle que la personne avait déjà.
        self._on_downloaded = on_downloaded
        self._lock = threading.Lock()
        self._snapshot = SetupSnapshot(IDLE, "", 0.0)
        # Mémoïsation de la RAM totale : constante de la machine, lue une seule fois (sous macOS
        # via un sous-processus ``sysctl``) plutôt qu'à chaque sondage de ``status`` par le front.
        # La disponibilité d'Ollama et la présence du modèle, elles, sont **re-sondées à chaque
        # appel** : ce sont les seules sources de vérité (un Ollama peut tomber, un modèle être
        # absent), et le sondage s'arrête de lui-même dès que le modèle est présent — le front
        # cesse alors d'interroger et la porte s'ouvre.
        self._memory_read = False
        self._memory_value: int | None = None

    def status(self) -> dict:
        """État de disponibilité du LLM : Ollama joignable, modèle présent, verdict RAM."""
        try:
            present = self._present(self._model, host=self._host)
            reachable = True
        except OllamaUnreachable:
            present, reachable = False, False
        memory = assess_memory(self._memory_total_bytes())
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
            # Bascule à RUNNING sous le **même** verrou que la garde : un 2e ``start`` concurrent
            # voit aussitôt RUNNING et renonce. Le check-and-set est ainsi atomique — plus de
            # fenêtre entre « pas en cours » et « marqué en cours » où deux appels lanceraient
            # deux téléchargements du même modèle.
            self._snapshot = SetupSnapshot(RUNNING, "pulling manifest", 0.0)

        # L'état vient d'être posé à RUNNING sous le verrou : toute sortie de ce bloc doit le
        # résoudre (``done``/``failed``), sinon un échec avant le spawn le laisserait figé sur
        # RUNNING à vie (les ``start`` suivants renoncent par idempotence → porte bloquée). On
        # rattrape donc aussi l'inattendu, pas seulement ``OllamaUnreachable``.
        try:
            if self._present(self._model, host=self._host):
                return self._set(SetupSnapshot(DONE, "success", 1.0))
            self._spawn(self._run)
        except OllamaUnreachable as exc:
            return self._set(SetupSnapshot(FAILED, "ollama injoignable", 0.0, error=str(exc)))
        except Exception as exc:  # noqa: BLE001 — jamais figer sur RUNNING ; l'erreur est consignée
            return self._set(
                SetupSnapshot(FAILED, "échec de la mise en route", 0.0, error=f"{type(exc).__name__}: {exc}")
            )

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
            self._record_download()
            self._set(SetupSnapshot(DONE, result.status, 1.0))

    def _record_download(self) -> None:
        """Signale le téléchargement réussi, sans jamais faire échouer le setup.

        Le modèle est bien là : si la trace de son origine ne s'écrit pas, il sera tenu pour déjà
        présent, donc jamais supprimé à tort. On rattrape **toute** exception, pas seulement les
        erreurs de disque : une exception qui s'échapperait arrêterait le thread avant le passage
        à ``done``, et l'écran de mise en route resterait bloqué sur ``running``.
        """
        if self._on_downloaded is None:
            return
        try:
            self._on_downloaded(self._model)
        except Exception:  # noqa: BLE001 — la trace d'origine ne doit jamais bloquer le setup
            pass

    def _on_progress(self, progress: PullProgress) -> None:
        self._set(SetupSnapshot(RUNNING, progress.status, progress.fraction))

    def _set(self, snapshot: SetupSnapshot) -> SetupSnapshot:
        with self._lock:
            self._snapshot = snapshot
            return snapshot

    def _memory_total_bytes(self) -> int | None:
        """RAM totale de la machine, lue **une seule fois** puis réutilisée (constante machine).

        Évite de refaire la lecture par OS (sous macOS, un sous-processus ``sysctl``) à chaque
        sondage de ``status``. Une valeur ``None`` (indéterminable) est elle aussi mémoïsée : elle
        ne deviendra pas déterminable au prochain appel.
        """
        if not self._memory_read:
            self._memory_value = self._total_memory()
            self._memory_read = True
        return self._memory_value

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
