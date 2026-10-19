"""Persistance des lettres de motivation en SQLite (V2, OPP-147).

``LetterStore`` enregistre et relit des ``Letter`` (via ``app.db``). L'écriture est un
**upsert** sur ``recommendation_id`` : régénérer ou rééditer la lettre d'une reco met à
jour sa ligne au lieu de la dupliquer (idempotence par reco, cf. critère d'acceptation).

Le métier dépend du protocole ``LetterRepository`` (et non de SQLite directement), à
l'image de ``DecisionRepository`` / ``OfferRepository``.
"""

from __future__ import annotations

import sqlite3
from typing import Protocol, runtime_checkable

from app.letter import Letter

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS letters (
    recommendation_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    source TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@runtime_checkable
class LetterRepository(Protocol):
    """Contrat de persistance des lettres consommé par le métier."""

    def save(self, letter: Letter) -> None: ...

    def get(self, recommendation_id: str) -> Letter | None: ...

    def updated_at_by_recommendation(self, recommendation_ids: list[str]) -> dict[str, str]: ...

    def delete(self, recommendation_id: str) -> bool: ...


class LetterStore:
    """Dépôt SQLite de lettres (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()

    @staticmethod
    def _row_to_letter(row: sqlite3.Row) -> Letter:
        return Letter(
            recommendation_id=row["recommendation_id"],
            body=row["body"],
            source=row["source"],
            model=row["model"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save(self, letter: Letter) -> None:
        """Insère la lettre ou met à jour la ligne existante (upsert sur la reco)."""
        self.conn.execute(
            "INSERT INTO letters "
            "(recommendation_id, body, source, model, created_at, updated_at) "
            "VALUES (:recommendation_id, :body, :source, :model, :created_at, :updated_at) "
            "ON CONFLICT(recommendation_id) DO UPDATE SET "
            "body=excluded.body, source=excluded.source, model=excluded.model, "
            "created_at=excluded.created_at, updated_at=excluded.updated_at",
            {
                "recommendation_id": letter.recommendation_id,
                "body": letter.body,
                "source": letter.source,
                "model": letter.model,
                "created_at": letter.created_at,
                "updated_at": letter.updated_at,
            },
        )
        self.conn.commit()

    def get(self, recommendation_id: str) -> Letter | None:
        """Retourne la lettre de la reco donnée, ou ``None`` si absente."""
        row = self.conn.execute(
            "SELECT * FROM letters WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        return None if row is None else self._row_to_letter(row)

    def updated_at_by_recommendation(self, recommendation_ids: list[str]) -> dict[str, str]:
        """``{recommendation_id: updated_at}`` des lettres existantes parmi ``recommendation_ids``.

        Lecture en lot (un seul ``SELECT ... IN (...)``) pour le flux d'activité du cockpit, afin
        d'éviter un accès par recommandation (N+1). Les recos sans lettre sont absentes de la table.
        """
        if not recommendation_ids:
            return {}
        placeholders = ",".join("?" * len(recommendation_ids))
        rows = self.conn.execute(
            f"SELECT recommendation_id, updated_at FROM letters "
            f"WHERE recommendation_id IN ({placeholders})",
            recommendation_ids,
        ).fetchall()
        return {row["recommendation_id"]: row["updated_at"] for row in rows}

    def delete(self, recommendation_id: str) -> bool:
        """Supprime la lettre de la reco ; ``True`` si une ligne a été retirée."""
        cursor = self.conn.execute(
            "DELETE FROM letters WHERE recommendation_id = ?", (recommendation_id,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Nombre de lettres stockées."""
        return self.conn.execute("SELECT COUNT(*) FROM letters").fetchone()[0]
