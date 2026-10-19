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
    status TEXT NOT NULL,
    applied_at TEXT
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

    def set_applied(self, recommendation_id: str, applied_at: str | None) -> None: ...

    def get_by_recommendation(self, recommendation_id: str) -> ApplicationAction | None: ...

    def applied_recommendation_ids(self, candidate_id: str) -> set[str]: ...

    def applied_at_by_recommendation(self, recommendation_ids: list[str]) -> dict[str, str]: ...


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
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Migrations idempotentes pour les bases créées avant un ajout de colonne.

        ``applied_at`` (cycle de vie « candidaté », OPP-xxx) a été ajouté après coup : une
        base existante a la table sans la colonne. On l'ajoute si elle manque — ``ALTER TABLE
        ADD COLUMN`` crée la colonne à ``NULL``, ce qui est exactement « intention notée mais
        pas encore candidaté » pour les lignes historiques.
        """
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(application_actions)")
        }
        if "applied_at" not in columns:
            self.conn.execute("ALTER TABLE application_actions ADD COLUMN applied_at TEXT")

    def save(self, action: ApplicationAction) -> None:
        self.conn.execute(
            "INSERT INTO application_actions "
            "(action_id, recommendation_id, candidate_id, decision_status_at_confirmation, "
            "confirmed_at, created_at, status, applied_at) "
            "VALUES (:action_id, :recommendation_id, :candidate_id, "
            ":decision_status_at_confirmation, :confirmed_at, :created_at, :status, :applied_at)",
            {
                "action_id": action.action_id,
                "recommendation_id": action.recommendation_id,
                "candidate_id": action.candidate_id,
                "decision_status_at_confirmation": action.decision_status_at_confirmation,
                "confirmed_at": action.confirmed_at,
                "created_at": action.created_at,
                "status": action.status,
                "applied_at": action.applied_at,
            },
        )
        self.conn.commit()

    def set_applied(self, recommendation_id: str, applied_at: str | None) -> None:
        """Pose ou retire la date de candidature **réellement effectuée** de l'action.

        ``applied_at`` non ``None`` = candidature déclarée (date) ; ``None`` = annulation (retour
        à l'état « intention notée »). L'appelant (``ActionService``) a déjà vérifié l'existence
        de l'action et porte l'idempotence ; ici on persiste simplement.
        """
        self.conn.execute(
            "UPDATE application_actions SET applied_at = ? WHERE recommendation_id = ?",
            (applied_at, recommendation_id),
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
            applied_at=row["applied_at"],
        )

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM application_actions").fetchone()[0]

    def applied_recommendation_ids(self, candidate_id: str) -> set[str]:
        """``recommendation_id`` des candidatures **déclarées** (``applied_at``) d'un candidat.

        Entonnoir du cockpit (OPP-163/164) : repère les offres réellement candidatées (étape
        « postulé ») ; une intention seule (sans ``applied_at``) n'y figure pas.
        """
        rows = self.conn.execute(
            "SELECT recommendation_id FROM application_actions "
            "WHERE candidate_id = ? AND applied_at IS NOT NULL",
            (candidate_id,),
        ).fetchall()
        return {row["recommendation_id"] for row in rows}

    def applied_at_by_recommendation(self, recommendation_ids: list[str]) -> dict[str, str]:
        """``{recommendation_id: applied_at}`` des candidatures **déclarées** parmi les ids donnés.

        Lecture en lot (un seul ``SELECT ... IN (...)``) pour le flux d'activité du cockpit : évite
        un accès par recommandation (N+1). Les intentions sans ``applied_at`` sont exclues.
        """
        if not recommendation_ids:
            return {}
        placeholders = ",".join("?" * len(recommendation_ids))
        rows = self.conn.execute(
            f"SELECT recommendation_id, applied_at FROM application_actions "
            f"WHERE recommendation_id IN ({placeholders}) AND applied_at IS NOT NULL",
            recommendation_ids,
        ).fetchall()
        return {row["recommendation_id"]: row["applied_at"] for row in rows}


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
