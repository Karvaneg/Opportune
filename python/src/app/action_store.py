"""Persistance des actions sensibles en SQLite (V2, OPP-096).

Deux dépôts **séparés** — un par type d'action — pour ne pas mélanger candidatures et
messages, et pour porter chacun sa propre clé d'idempotence :

- ``ApplicationActionStore`` : une candidature **au plus** par ``recommendation_id`` ;
- ``OutboundMessageActionStore`` : un message **au plus** par ``contact_id``.

L'unicité est garantie en base (colonne ``UNIQUE`` sur la cible) — filet défensif ; la
logique d'idempotence (« deuxième confirmation = même résultat, sans nouvelle action »)
est portée par ``ActionService`` qui lit avant d'écrire. Le métier dépend des protocoles,
pas de SQLite directement.
"""

from __future__ import annotations

import sqlite3
from typing import Protocol, runtime_checkable

from app.action import ApplicationAction, OutboundMessageAction

_CREATE_APPLICATIONS = """
CREATE TABLE IF NOT EXISTS application_actions (
    action_id TEXT PRIMARY KEY,
    recommendation_id TEXT NOT NULL UNIQUE,
    candidate_id TEXT NOT NULL,
    decision_status_at_confirmation TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

_CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS outbound_message_actions (
    action_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL UNIQUE,
    recommendation_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
)
"""


@runtime_checkable
class ApplicationActionRepository(Protocol):
    """Contrat de persistance des candidatures confirmées."""

    def save(self, action: ApplicationAction) -> None: ...

    def get_by_recommendation(self, recommendation_id: str) -> ApplicationAction | None: ...


@runtime_checkable
class OutboundMessageActionRepository(Protocol):
    """Contrat de persistance des messages de contact confirmés."""

    def save(self, action: OutboundMessageAction) -> None: ...

    def get_by_contact(self, contact_id: str) -> OutboundMessageAction | None: ...


class ApplicationActionStore:
    """Dépôt SQLite des candidatures confirmées (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_APPLICATIONS)
        self.conn.commit()

    def save(self, action: ApplicationAction) -> None:
        self.conn.execute(
            "INSERT INTO application_actions "
            "(action_id, recommendation_id, candidate_id, decision_status_at_confirmation, "
            "confirmed_at, created_at, status) "
            "VALUES (:action_id, :recommendation_id, :candidate_id, "
            ":decision_status_at_confirmation, :confirmed_at, :created_at, :status)",
            {
                "action_id": action.action_id,
                "recommendation_id": action.recommendation_id,
                "candidate_id": action.candidate_id,
                "decision_status_at_confirmation": action.decision_status_at_confirmation,
                "confirmed_at": action.confirmed_at,
                "created_at": action.created_at,
                "status": action.status,
            },
        )
        self.conn.commit()

    def get_by_recommendation(self, recommendation_id: str) -> ApplicationAction | None:
        row = self.conn.execute(
            "SELECT * FROM application_actions WHERE recommendation_id = ?",
            (recommendation_id,),
        ).fetchone()
        if row is None:
            return None
        return ApplicationAction(
            action_id=row["action_id"],
            recommendation_id=row["recommendation_id"],
            candidate_id=row["candidate_id"],
            decision_status_at_confirmation=row["decision_status_at_confirmation"],
            confirmed_at=row["confirmed_at"],
            created_at=row["created_at"],
            status=row["status"],
        )

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM application_actions").fetchone()[0]


class OutboundMessageActionStore:
    """Dépôt SQLite des messages de contact confirmés (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_MESSAGES)
        self.conn.commit()

    def save(self, action: OutboundMessageAction) -> None:
        self.conn.execute(
            "INSERT INTO outbound_message_actions "
            "(action_id, contact_id, recommendation_id, candidate_id, confirmed_at, "
            "created_at, status) "
            "VALUES (:action_id, :contact_id, :recommendation_id, :candidate_id, "
            ":confirmed_at, :created_at, :status)",
            {
                "action_id": action.action_id,
                "contact_id": action.contact_id,
                "recommendation_id": action.recommendation_id,
                "candidate_id": action.candidate_id,
                "confirmed_at": action.confirmed_at,
                "created_at": action.created_at,
                "status": action.status,
            },
        )
        self.conn.commit()

    def get_by_contact(self, contact_id: str) -> OutboundMessageAction | None:
        row = self.conn.execute(
            "SELECT * FROM outbound_message_actions WHERE contact_id = ?", (contact_id,)
        ).fetchone()
        if row is None:
            return None
        return OutboundMessageAction(
            action_id=row["action_id"],
            contact_id=row["contact_id"],
            recommendation_id=row["recommendation_id"],
            candidate_id=row["candidate_id"],
            confirmed_at=row["confirmed_at"],
            created_at=row["created_at"],
            status=row["status"],
        )

    def count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM outbound_message_actions"
        ).fetchone()[0]
