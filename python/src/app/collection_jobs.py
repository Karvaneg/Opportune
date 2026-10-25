"""Registre de jobs de collecte asynchrone (V2, OPP-170).

La collecte réelle paie un passage LLM par offre neuve (~40 s/offre en local) : l'exécuter
dans le fil de la requête HTTP gèle le serveur (séquentiel) et fait timeouter le client. Ce
registre déporte une passe dans un **thread de fond** et expose son avancement par sondage :

    POST /collect        → start() lance le job, rend un ``job_id`` immédiatement
    GET  /collect/{id}   → get() rend statut + progression + bilan final

**Un seul job à la fois.** L'orchestrateur partage une base SQLite ; faire coexister une
écriture de job et les lectures de l'API est déjà le cas limite qu'on sécurise (WAL +
``busy_timeout``, cf. ``app.db``). On ne multiplie pas les écrivains : ``start`` refuse
(``CollectionAlreadyRunning``) tant qu'un job tourne. Les jobs terminés restent consultables
(le front sonde jusqu'au bilan) ; leur nombre est borné par cette unicité côté usage dogfood.

Le **runner** (le travail bloquant : assembler la source, ``run_collection`` sur une
connexion dédiée) est injecté — le registre ne connaît ni Adzuna, ni le LLM, ni la base. Le
**spawn** du thread est injectable aussi, pour des tests déterministes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import Callable, Protocol, runtime_checkable
from uuid import uuid4

from app.offer_collection import CollectionProgress, CollectionReport

# Statuts d'un job de collecte. ``running`` dès le lancement ; ``done`` quand le runner rend un
# bilan (même porteur d'un ``source_error`` — une panne de source n'est pas un échec de job) ;
# ``failed`` seulement sur exception inattendue du runner.
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

ProgressCallback = Callable[[CollectionProgress], None]

# Nombre de jobs conservés en mémoire. Les jobs terminés restent consultables (le front sonde
# jusqu'au bilan), mais l'unicité de l'écrivain borne déjà l'usage à ~un job à la fois : on ne
# garde que les plus récents pour éviter une croissance indéfinie de la map sur un serveur
# long-vivant. Le job actif n'est jamais évincé (cf. ``_prune_locked``).
_MAX_RETAINED_JOBS = 8

_EMPTY_PROGRESS = CollectionProgress(
    collected=0, stored=0, duplicates=0, failures=0, enriched=0, enriched_recovered=0
)


class CollectionAlreadyRunning(Exception):
    """Levée par ``start`` quand un job de collecte est déjà en cours (unicité)."""


@runtime_checkable
class CollectionRunner(Protocol):
    """Travail bloquant d'une passe de collecte, injecté dans le registre.

    Reçoit les critères de recherche et un callback de progression ; retourne un
    ``CollectionReport``. Doit ouvrir sa **propre** connexion SQLite (il tourne dans le
    thread du job, pas celui de l'API). Une panne de source est rendue dans le bilan
    (``source_error``), pas levée.
    """

    def __call__(
        self,
        *,
        what: str,
        where: str,
        max_offers: int,
        on_progress: ProgressCallback,
        should_cancel: Callable[[], bool],
    ) -> CollectionReport: ...


@dataclass(frozen=True)
class CollectionJob:
    """Instantané immuable de l'état d'un job (rendu par ``get``, jamais muté en place)."""

    id: str
    status: str
    progress: CollectionProgress
    report: CollectionReport | None = None
    error: str | None = None
    # Arrêt coopératif demandé (OPP-209) : vrai dès qu'un ``cancel`` a été accepté, tant que le
    # runner n'a pas atteint son prochain point de contrôle — de quoi afficher « arrêt en cours ».
    cancel_requested: bool = False


class CollectionJobRegistry:
    """Lance et suit des jobs de collecte de fond, un seul actif à la fois (OPP-170)."""

    def __init__(
        self,
        runner: CollectionRunner,
        *,
        spawn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._runner = runner
        # Spawn par défaut : un thread démon (ne bloque pas l'arrêt du process). Injectable
        # pour des tests déterministes (exécution synchrone, ou thread piloté par un Event).
        self._spawn = spawn or _spawn_daemon
        self._lock = threading.Lock()
        self._jobs: dict[str, CollectionJob] = {}
        self._active: str | None = None
        # Drapeau d'arrêt coopératif par job (OPP-209) : posé par ``cancel``, consulté par le
        # runner via ``should_cancel``. Retiré à la fin du job (``_finish``).
        self._cancel_events: dict[str, threading.Event] = {}

    def start(self, *, what: str, where: str, max_offers: int) -> str:
        """Enregistre un job ``running`` et lance la passe en fond ; rend son ``job_id``.

        Lève ``CollectionAlreadyRunning`` si un job est déjà en cours (unicité de l'écrivain).
        """
        with self._lock:
            if self._active is not None:
                raise CollectionAlreadyRunning(
                    "une collecte est déjà en cours ; réessayez une fois terminée"
                )
            job_id = uuid4().hex
            self._jobs[job_id] = CollectionJob(
                id=job_id, status=RUNNING, progress=_EMPTY_PROGRESS
            )
            self._active = job_id
            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
            self._prune_locked()

        params = {"what": what, "where": where, "max_offers": max_offers}
        self._spawn(lambda: self._run(job_id, params, cancel_event))
        return job_id

    def cancel(self, job_id: str) -> bool:
        """Demande l'arrêt coopératif d'un job **actif** ; rend ``True`` si pris en compte (OPP-209).

        Pose le drapeau que le runner consulte entre deux offres : l'arrêt est effectif au
        prochain point de contrôle (l'intake en cours n'est pas interrompu). Marque le job
        ``cancel_requested`` pour un retour « arrêt en cours » côté front. Rend ``False`` si le
        job est inconnu ou déjà terminé (rien à annuler). Idempotent.
        """
        with self._lock:
            event = self._cancel_events.get(job_id)
            job = self._jobs.get(job_id)
            if event is None or job is None or job.status != RUNNING:
                return False
            event.set()
            self._jobs[job_id] = replace(job, cancel_requested=True)
            return True

    def get(self, job_id: str) -> CollectionJob | None:
        """Instantané courant du job, ou ``None`` s'il est inconnu."""
        with self._lock:
            return self._jobs.get(job_id)

    def active_job(self) -> CollectionJob | None:
        """Instantané du job **actif** (``running``), ou ``None`` si aucune collecte en cours.

        Source du suivi **global** (OPP-208) : le front interroge l'état courant sans connaître
        de ``job_id`` (il le perd en changeant de page). Seul le job actif est rendu — un job
        terminé n'est plus « actif » (son bilan final reste lisible par ``get(job_id)``).
        """
        with self._lock:
            return self._jobs.get(self._active) if self._active is not None else None

    def _prune_locked(self) -> None:
        """Borne la map à ``_MAX_RETAINED_JOBS`` en évinçant les terminés les plus anciens.

        À appeler **sous verrou**. ``dict`` préserve l'ordre d'insertion → les premières clés
        sont les plus anciennes. Le job actif est préservé quelle que soit sa position (il n'est
        de toute façon jamais le plus ancien dès qu'on dépasse le seuil en usage normal).
        """
        while len(self._jobs) > _MAX_RETAINED_JOBS:
            for job_id in self._jobs:
                if job_id != self._active:
                    del self._jobs[job_id]
                    break
            else:  # plus rien à évincer (ne reste que le job actif)
                break

    def _run(self, job_id: str, params: dict, cancel_event: threading.Event) -> None:
        """Corps exécuté dans le thread du job : lance le runner, publie progression et issue."""

        def on_progress(progress: CollectionProgress) -> None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None:
                    self._jobs[job_id] = replace(job, progress=progress)

        try:
            report = self._runner(
                on_progress=on_progress, should_cancel=cancel_event.is_set, **params
            )
        except Exception as exc:  # noqa: BLE001 — consigné dans le job, jamais avalé
            self._finish(job_id, status=FAILED, error=f"{type(exc).__name__}: {exc}")
            return
        # Issue décidée d'après ce que le runner a **réellement** fait (``report.cancelled``),
        # non d'après une relecture du drapeau : une annulation qui arrive une fois la dernière
        # offre traitée ne tronque rien → le job reste ``done`` (bilan complet), jamais figé à
        # tort en ``cancelled`` (course fin-de-passe / ``cancel`` concurrent, OPP-209).
        status = CANCELLED if report.cancelled else DONE
        self._finish(job_id, status=status, report=report)

    def _finish(
        self,
        job_id: str,
        *,
        status: str,
        report: CollectionReport | None = None,
        error: str | None = None,
    ) -> None:
        """Fige l'issue du job et libère le créneau actif (sous verrou)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                self._jobs[job_id] = replace(
                    job, status=status, report=report, error=error
                )
            if self._active == job_id:
                self._active = None
            self._cancel_events.pop(job_id, None)


def _spawn_daemon(target: Callable[[], None]) -> None:
    """Lance ``target`` dans un thread démon (spawn par défaut du registre)."""
    threading.Thread(target=target, daemon=True).start()
