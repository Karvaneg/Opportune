"""Registre du périmètre : les candidats (« recherches ») connus de l'espace (V2, OPP-183).

Jusqu'ici le périmètre (``owned_candidates``) était un ``frozenset`` **figé au boot** depuis la
variable d'environnement ``OPPORTUNE_API_CANDIDATES`` (cf. ``api.server``). OPP-183 le rend
**dynamique et stocké en base** : ce registre liste les candidats de l'espace courant, et l'auth
en dérive le périmètre à chaque requête.

Un candidat du registre existe **indépendamment de son profil** : il peut être enrôlé sans CV
encore (état « nouveau profil »), ce qui laisse le cockpit afficher le guide d'accueil plutôt
qu'un « aucun candidat ». Périmètre et profil sont donc deux notions distinctes — c'est ce qui
permet au « repartir de zéro » de la démo de garder un slot vide à renseigner.

Neutre de vocabulaire : on parle de *candidat* ici (clé technique partagée avec profils /
décisions / offres). Le nom produit « recherche » et la création/renommage sont l'objet d'OPP-184.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
)
"""


class CandidateRegistry:
    """Dépôt SQLite du périmètre : les ids de candidats de l'espace (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()

    def list_ids(self) -> list[str]:
        """Ids du périmètre (ordre d'id) — source du ``owned_candidates`` de l'auth."""
        return [row[0] for row in self.conn.execute("SELECT id FROM candidates ORDER BY id")]

    def add(self, candidate_id: str) -> None:
        """Enrôle un candidat dans le périmètre (idempotent : réinsérer ne duplique pas)."""
        self.conn.execute(
            "INSERT INTO candidates (id, created_at) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
            (candidate_id, _utcnow_iso()),
        )
        self.conn.commit()

    def ensure(self, candidate_ids: Iterable[str]) -> None:
        """Enrôle plusieurs candidats d'un coup (insert-or-ignore). Vides/doublons ignorés."""
        rows = [(cid, _utcnow_iso()) for cid in candidate_ids if cid]
        if not rows:
            return
        self.conn.executemany(
            "INSERT INTO candidates (id, created_at) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
            rows,
        )
        self.conn.commit()
