"""Suivi persistant des soumissions Discord (V2, OPP-131).

Idempotence du re-run push : mémoriser quelle recommandation a **déjà une carte vivante**
en revue, pour ne pas la re-pousser tant qu'elle n'est pas tranchée. Ce suivi est
**distinct du statut de validation** — une carte poussée reste ``pending`` jusqu'au clic
humain (elle doit le rester pour être validable via le receive, OPP-125). S'appuyer sur le
statut ne suffirait donc pas : d'où ce registre dédié (mapping ``recommendation_id`` ↔
message Discord).

Le métier dépend du protocole ``SubmissionRepository`` (et non de SQLite directement).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS submissions (
    recommendation_id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    submitted_at TEXT NOT NULL
)
"""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Submission:
    """Une carte de revue vivante : la recommandation et le message Discord qui la porte."""

    recommendation_id: str
    message_id: str
    channel_id: str
    submitted_at: str  # ISO 8601


@runtime_checkable
class SubmissionRepository(Protocol):
    """Contrat de suivi des soumissions consommé par la boucle push."""

    def record(
        self, recommendation_id: str, message_id: str, channel_id: str,
        *, submitted_at: str | None = None,
    ) -> None: ...

    def has_open_submission(self, recommendation_id: str) -> bool: ...

    def forget(self, recommendation_id: str) -> None: ...


class SubmissionStore:
    """Dépôt SQLite des soumissions Discord (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()

    def record(
        self,
        recommendation_id: str,
        message_id: str,
        channel_id: str,
        *,
        submitted_at: str | None = None,
    ) -> None:
        """Enregistre (ou met à jour) la soumission d'une recommandation — upsert sur l'id.

        Réenregistrer la même recommandation rafraîchit le message associé au lieu de
        dupliquer : une re-soumission après oubli (message supprimé côté Discord) repart
        proprement sur la nouvelle carte.
        """
        self.conn.execute(
            "INSERT INTO submissions (recommendation_id, message_id, channel_id, submitted_at) "
            "VALUES (:rid, :mid, :cid, :at) "
            "ON CONFLICT(recommendation_id) DO UPDATE SET "
            "message_id=excluded.message_id, channel_id=excluded.channel_id, "
            "submitted_at=excluded.submitted_at",
            {
                "rid": recommendation_id,
                "mid": message_id,
                "cid": channel_id,
                "at": submitted_at or _utcnow_iso(),
            },
        )
        self.conn.commit()

    def has_open_submission(self, recommendation_id: str) -> bool:
        """La recommandation a-t-elle déjà une carte en revue (non oubliée) ?"""
        row = self.conn.execute(
            "SELECT 1 FROM submissions WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        return row is not None

    def get(self, recommendation_id: str) -> Submission | None:
        """Retourne la soumission d'une recommandation, ou ``None`` si aucune."""
        row = self.conn.execute(
            "SELECT * FROM submissions WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        if row is None:
            return None
        return Submission(
            recommendation_id=row["recommendation_id"],
            message_id=row["message_id"],
            channel_id=row["channel_id"],
            submitted_at=row["submitted_at"],
        )

    def forget(self, recommendation_id: str) -> None:
        """Oublie la soumission (no-op si absente) : autorise une re-soumission.

        À appeler quand la carte n'est plus valable côté Discord (message supprimé) pour que
        le prochain run la re-pousse. La détection de suppression (event gateway) relève du
        receive et n'est pas câblée ici.
        """
        self.conn.execute(
            "DELETE FROM submissions WHERE recommendation_id = ?", (recommendation_id,)
        )
        self.conn.commit()

    def count(self) -> int:
        """Nombre de soumissions suivies (utile aux vérifications)."""
        return self.conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
