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
from typing import Protocol, runtime_checkable

from hermes.models import HermesRun, OfferEvaluation

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

    def count(self) -> int:
        """Nombre d'exécutions stockées."""
        return self.conn.execute("SELECT COUNT(*) FROM hermes_runs").fetchone()[0]
