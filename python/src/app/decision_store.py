"""Persistance des décisions en SQLite (V2, OPP-057).

``DecisionStore`` enregistre et met à jour des ``Decision`` (via ``app.db``). L'écriture
est un **upsert** sur l'``id`` (couple candidat/offre) : re-valider une décision met à
jour sa ligne au lieu de la dupliquer. L'historique est sérialisé en JSON, ce qui
garantit que la décision, ses dates et la recommandation d'origine restent consultables.

Le métier dépend du protocole ``DecisionRepository`` (et non de SQLite directement).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Protocol, runtime_checkable

from app.decision import Decision, DecisionEvent

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    score INTEGER NOT NULL,
    justification TEXT NOT NULL,
    status TEXT NOT NULL,
    comment TEXT,
    history TEXT NOT NULL
)
"""


@runtime_checkable
class DecisionRepository(Protocol):
    """Contrat de persistance de décisions consommé par le métier."""

    def save(self, decision: Decision) -> None: ...

    def get(self, decision_id: str) -> Decision | None: ...

    def list_for_candidate(self, candidate_id: str) -> list[Decision]: ...


class DecisionStore:
    """Dépôt SQLite de décisions (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> Decision:
        history = tuple(DecisionEvent(**event) for event in json.loads(row["history"]))
        return Decision(
            id=row["id"],
            candidate_id=row["candidate_id"],
            offer_id=row["offer_id"],
            action=row["action"],
            score=row["score"],
            justification=row["justification"],
            status=row["status"],
            comment=row["comment"],
            history=history,
        )

    def save(self, decision: Decision) -> None:
        """Insère la décision ou met à jour la ligne existante (upsert sur ``id``)."""
        history = json.dumps(
            [
                {"status": e.status, "at": e.at, "comment": e.comment}
                for e in decision.history
            ],
            ensure_ascii=False,
        )
        self.conn.execute(
            "INSERT INTO decisions "
            "(id, candidate_id, offer_id, action, score, justification, status, comment, history) "
            "VALUES (:id, :candidate_id, :offer_id, :action, :score, :justification, :status, :comment, :history) "
            "ON CONFLICT(id) DO UPDATE SET "
            "action=excluded.action, score=excluded.score, justification=excluded.justification, "
            "status=excluded.status, comment=excluded.comment, history=excluded.history",
            {
                "id": decision.id,
                "candidate_id": decision.candidate_id,
                "offer_id": decision.offer_id,
                "action": decision.action,
                "score": decision.score,
                "justification": decision.justification,
                "status": decision.status,
                "comment": decision.comment,
                "history": history,
            },
        )
        self.conn.commit()

    def get(self, decision_id: str) -> Decision | None:
        """Retourne la décision d'``id`` donné, ou ``None`` si absente."""
        row = self.conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        return None if row is None else self._row_to_decision(row)

    def list_for_candidate(self, candidate_id: str) -> list[Decision]:
        """Retourne les décisions d'un candidat (ordonnées par ``id``)."""
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE candidate_id = ? ORDER BY id", (candidate_id,)
        ).fetchall()
        return [self._row_to_decision(row) for row in rows]

    def count(self) -> int:
        """Nombre de décisions stockées."""
        return self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
