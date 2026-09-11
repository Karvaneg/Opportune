"""Persistance des exécutions Hermes en SQLite (V2, OPP-092).

``RunStore`` journalise chaque exécution d'Hermes (``HermesRun``) via ``app.db``.
Chaque exécution porte un ``run_id`` unique et reste tracée **distinctement** : les runs
ne sont jamais dédupliqués (deux exécutions du même candidat produisent deux lignes).
L'idempotence métier — ne pas dupliquer les *décisions* d'un candidat à l'autre — est
garantie en amont par ``DecisionService.decide`` (upsert sur le couple candidat/offre),
pas ici. L'``ON CONFLICT(run_id)`` de ``save`` n'est qu'une protection défensive contre
un ré-enregistrement du *même* run. Les évaluations (offres/scores/décisions) et les
erreurs sont sérialisées en JSON, gardant la trace consultable a posteriori.

Le métier dépend du protocole ``RunRepository`` (et non de SQLite directement), d'où
l'injection possible d'une fausse persistance en test.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Collection
from typing import Protocol, runtime_checkable

from hermes.models import HermesRun, HermesRunSummary, OfferEvaluation

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS hermes_runs (
    run_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    executed_at TEXT NOT NULL,
    evaluations TEXT NOT NULL,
    errors TEXT NOT NULL
)
"""


@runtime_checkable
class RunRepository(Protocol):
    """Contrat de persistance des exécutions Hermes consommé par l'orchestrateur."""

    def save(self, run: HermesRun) -> None: ...

    def get(self, run_id: str) -> HermesRun | None: ...

    def delete(self, run_id: str) -> bool: ...

    def list_run_summaries(
        self,
        candidate_ids: Collection[str] | None = None,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[HermesRunSummary], int]: ...


class RunStore:
    """Dépôt SQLite des exécutions Hermes (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> HermesRun:
        evaluations = tuple(
            OfferEvaluation(**item) for item in json.loads(row["evaluations"])
        )
        errors = tuple(json.loads(row["errors"]))
        return HermesRun(
            run_id=row["run_id"],
            candidate_id=row["candidate_id"],
            executed_at=row["executed_at"],
            evaluations=evaluations,
            errors=errors,
        )

    def save(self, run: HermesRun) -> None:
        """Insère l'exécution (le ``ON CONFLICT`` ne protège que le ré-enregistrement du même ``run_id``)."""
        evaluations = json.dumps(
            [
                {
                    "offer_id": e.offer_id,
                    "score": e.score,
                    "decision_status": e.decision_status,
                    "advisory_status": e.advisory_status,
                    "action": e.action,
                    "title": e.title,
                    "company": e.company,
                    "justification": e.justification,
                }
                for e in run.evaluations
            ],
            ensure_ascii=False,
        )
        errors = json.dumps(list(run.errors), ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO hermes_runs (run_id, candidate_id, executed_at, evaluations, errors) "
            "VALUES (:run_id, :candidate_id, :executed_at, :evaluations, :errors) "
            "ON CONFLICT(run_id) DO UPDATE SET "
            "candidate_id=excluded.candidate_id, executed_at=excluded.executed_at, "
            "evaluations=excluded.evaluations, errors=excluded.errors",
            {
                "run_id": run.run_id,
                "candidate_id": run.candidate_id,
                "executed_at": run.executed_at,
                "evaluations": evaluations,
                "errors": errors,
            },
        )
        self.conn.commit()

    def get(self, run_id: str) -> HermesRun | None:
        """Retourne l'exécution d'``run_id`` donné, ou ``None`` si absente."""
        row = self.conn.execute(
            "SELECT * FROM hermes_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return None if row is None else self._row_to_run(row)

    def delete(self, run_id: str) -> bool:
        """Supprime l'exécution d'``run_id`` ; ``True`` si une ligne a été retirée (OPP-144).

        Idempotent : une seconde suppression du même ``run_id`` retourne ``False`` (rien à
        retirer) — l'appelant en fait un 404 neutre. Ne touche pas aux décisions : celles-ci
        vivent dans ``DecisionStore`` et gardent leur historique de validation humaine.
        """
        cursor = self.conn.execute("DELETE FROM hermes_runs WHERE run_id = ?", (run_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def list_for_candidate(self, candidate_id: str) -> list[HermesRun]:
        """Retourne les exécutions d'un candidat, dans l'ordre chronologique.

        Tri par ``executed_at`` puis, à égalité de date, par ``rowid`` (ordre d'insertion) :
        le tie-break reste chronologique même quand ``run_id`` est un uuid non monotone.
        """
        rows = self.conn.execute(
            "SELECT * FROM hermes_runs WHERE candidate_id = ? ORDER BY executed_at, rowid",
            (candidate_id,),
        ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def list_run_summaries(
        self,
        candidate_ids: Collection[str] | None = None,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[HermesRunSummary], int]:
        """Résumés de runs **paginés** (plus récents d'abord) + cardinal **total** du périmètre.

        La volumétrie (``evaluation_count`` / ``error_count``) est calculée en **SQL**
        (``json_array_length``) : aucun snapshot d'offre n'est désérialisé et seule la page
        demandée est lue (``LIMIT`` / ``OFFSET``), au lieu de matérialiser toute la table.

        ``candidate_ids=None`` → **tous** les runs (mode ouvert). Sinon, restreint au
        périmètre fourni : un périmètre **vide** renvoie ``([], 0)`` sans requête. Le filtre
        passe par une **table temporaire jointe** plutôt qu'une clause ``IN (?, ?, …)``, ce
        qui reste robuste pour un large périmètre (au-delà de la limite de variables liées de
        SQLite). Tri antéchronologique (``executed_at`` DESC, ``rowid`` DESC) : le tie-break
        ``rowid`` reste stable même quand ``run_id`` est un uuid non monotone.
        """
        select = (
            "SELECT run_id, candidate_id, executed_at, "
            "json_array_length(evaluations) AS evaluation_count, "
            "json_array_length(errors) AS error_count "
            "FROM hermes_runs{where} "
            "ORDER BY executed_at DESC, rowid DESC LIMIT ? OFFSET ?"
        )
        count = "SELECT COUNT(*) FROM hermes_runs{where}"

        if candidate_ids is None:
            where = ""
            params: tuple = ()
        else:
            ids = list(candidate_ids)
            if not ids:
                return [], 0
            self._load_scope(ids)
            where = " WHERE candidate_id IN (SELECT candidate_id FROM _run_scope)"
            params = ()

        total = self.conn.execute(count.format(where=where), params).fetchone()[0]
        rows = self.conn.execute(
            select.format(where=where), (*params, limit, offset)
        ).fetchall()
        return [self._row_to_summary(row) for row in rows], total

    def _load_scope(self, ids: list[str]) -> None:
        """(Re)charge le périmètre courant dans une table temporaire ``_run_scope``.

        Réutilisée d'un appel à l'autre (``CREATE … IF NOT EXISTS`` + purge) pour filtrer les
        runs par jointure sans dépendre du nombre de placeholders d'une clause ``IN``.
        """
        self.conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _run_scope (candidate_id TEXT PRIMARY KEY)"
        )
        self.conn.execute("DELETE FROM _run_scope")
        self.conn.executemany(
            "INSERT OR IGNORE INTO _run_scope (candidate_id) VALUES (?)",
            [(candidate_id,) for candidate_id in ids],
        )

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> HermesRunSummary:
        return HermesRunSummary(
            run_id=row["run_id"],
            candidate_id=row["candidate_id"],
            executed_at=row["executed_at"],
            evaluation_count=row["evaluation_count"],
            error_count=row["error_count"],
        )

    def count(self) -> int:
        """Nombre d'exécutions stockées."""
        return self.conn.execute("SELECT COUNT(*) FROM hermes_runs").fetchone()[0]
