"""Persistance du suivi post-candidature en SQLite (OPP-223).

Une table d'événements **append-only** : une ligne par événement de suivi, rattachée à une
candidature (``recommendation_id``). On n'écrase jamais — l'historique se lit dans l'ordre
d'insertion (``id`` auto-incrémenté), qui est l'ordre chronologique d'enregistrement.

Choix d'une table dédiée (plutôt qu'un blob JSON sur la candidature) : les événements se
requêtent (lecture par candidature) et restent découplés du
cycle de vie de l'``ApplicationAction``. Le métier dépend du protocole
``ApplicationTrackingRepository`` (et non de SQLite directement).
"""

from __future__ import annotations

import sqlite3
from typing import Protocol, runtime_checkable

from app.application_tracking import TrackingEvent

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS application_tracking_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    at TEXT NOT NULL,
    event_date TEXT,
    comment TEXT
)
"""

_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_tracking_recommendation "
    "ON application_tracking_events (recommendation_id)"
)


@runtime_checkable
class ApplicationTrackingRepository(Protocol):
    """Contrat de persistance du suivi post-candidature consommé par le métier."""

    def append(
        self, recommendation_id: str, candidate_id: str, event: TrackingEvent
    ) -> None: ...

    def history(self, recommendation_id: str) -> tuple[TrackingEvent, ...]: ...

    def events_for(
        self, recommendation_ids: list[str]
    ) -> dict[str, tuple[TrackingEvent, ...]]: ...


class ApplicationTrackingStore:
    """Dépôt SQLite du suivi post-candidature (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.execute(_CREATE_INDEX)
        self.conn.commit()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> TrackingEvent:
        return TrackingEvent(
            kind=row["kind"],
            at=row["at"],
            event_date=row["event_date"],
            comment=row["comment"],
        )

    def append(
        self, recommendation_id: str, candidate_id: str, event: TrackingEvent
    ) -> None:
        """Ajoute un événement de suivi (append-only : jamais d'écrasement)."""
        self.conn.execute(
            "INSERT INTO application_tracking_events "
            "(recommendation_id, candidate_id, kind, at, event_date, comment) "
            "VALUES (:recommendation_id, :candidate_id, :kind, :at, :event_date, :comment)",
            {
                "recommendation_id": recommendation_id,
                "candidate_id": candidate_id,
                "kind": event.kind,
                "at": event.at,
                "event_date": event.event_date,
                "comment": event.comment,
            },
        )
        self.conn.commit()

    def history(self, recommendation_id: str) -> tuple[TrackingEvent, ...]:
        """Retourne l'historique d'une candidature, dans l'ordre chronologique d'enregistrement."""
        rows = self.conn.execute(
            "SELECT * FROM application_tracking_events "
            "WHERE recommendation_id = ? ORDER BY id",
            (recommendation_id,),
        ).fetchall()
        return tuple(self._row_to_event(row) for row in rows)

    def events_for(
        self, recommendation_ids: list[str]
    ) -> dict[str, tuple[TrackingEvent, ...]]:
        """``{recommendation_id: historique}`` pour plusieurs candidatures en un seul SELECT.

        Lecture en lot pour le flux d'activité du cockpit : évite un accès par recommandation
        (N+1). Groupement en O(n) (``list.append`` puis fige en tuple) ; les candidatures sans
        aucun événement sont absentes du dictionnaire.
        """
        if not recommendation_ids:
            return {}
        placeholders = ",".join("?" * len(recommendation_ids))
        rows = self.conn.execute(
            f"SELECT * FROM application_tracking_events "
            f"WHERE recommendation_id IN ({placeholders}) ORDER BY id",
            recommendation_ids,
        ).fetchall()
        grouped: dict[str, list[TrackingEvent]] = {}
        for row in rows:
            grouped.setdefault(row["recommendation_id"], []).append(self._row_to_event(row))
        return {rid: tuple(events) for rid, events in grouped.items()}

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM application_tracking_events"
        ).fetchone()[0]
