"""Appartenance des offres aux recherches (V2, OPP-186).

Jusqu'ici les offres formaient un **pot commun** : toutes les recherches d'un espace voyaient
toutes les offres collectées ou ajoutées, quelle que soit la recherche qui les avait fait entrer.
OPP-186 rend les offres **propres à chaque recherche** : ce dépôt tient la table de liens
``candidate_offers(candidate_id, offer_id, created_at)`` qui dit quelle recherche voit quelle offre.

La table ``offers`` reste **commune** (stockage et dédoublonnage par id calculé sur le contenu) :
une même offre collectée par deux recherches = une ligne ``offers`` + deux liens. Seule la
**visibilité** est propre à la recherche.

La date du lien (``created_at``) est la date d'**entrée de l'offre dans la recherche** : une offre
déjà en base, collectée aujourd'hui par une autre recherche, est récente pour celle-ci. Le catalogue
d'une recherche est trié sur cette date.

Migration : à la création de la table, chaque offre déjà présente est rattachée à **toutes** les
recherches de la base (``candidates``), avec la date d'entrée de l'offre en base (l'ordre du
catalogue ne bouge donc pas). Rien ne disparaît pour une recherche existante ; une recherche créée
ensuite part sans offre.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

_TABLE = "candidate_offers"

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    candidate_id TEXT NOT NULL,
    offer_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (candidate_id, offer_id)
)
"""

# Liens d'une recherche, entrées les plus récentes d'abord (``id`` en départage). La jointure
# écarte un lien vers une offre absente.
_SELECT_LINKS = f"""
SELECT l.offer_id, l.created_at FROM {_TABLE} AS l JOIN offers AS o ON o.id = l.offer_id
WHERE l.candidate_id = ?
ORDER BY l.created_at DESC, l.offer_id
"""


def _utcnow_iso() -> str:
    """Horodatage du lien : instant courant UTC en ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def remap_offer_id(conn: sqlite3.Connection, old_id: str, new_id: str) -> None:
    """Reporte les liens d'une offre dont l'id change (migration d'``OfferStore``, OPP-119).

    Sans table de liens (base antérieure à OPP-186), rien à faire. Un lien déjà présent sous le
    nouvel id (deux liens fusionnés en une même offre) est conservé, le doublon est supprimé.
    """
    if not _table_exists(conn, _TABLE):
        return
    conn.execute(
        f"UPDATE OR IGNORE {_TABLE} SET offer_id = ? WHERE offer_id = ?", (new_id, old_id)
    )
    conn.execute(f"DELETE FROM {_TABLE} WHERE offer_id = ?", (old_id,))


@runtime_checkable
class CandidateOfferRepository(Protocol):
    """Contrat d'appartenance offre ↔ recherche consommé par le métier."""

    def link(self, candidate_id: str, offer_id: str) -> None: ...

    def is_linked(self, candidate_id: str, offer_id: str) -> bool: ...

    def links(
        self, candidate_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[tuple[str, str]]: ...

    def offer_ids(
        self, candidate_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[str]: ...

    def count(self, candidate_id: str) -> int: ...


class CandidateOfferStore:
    """Dépôt SQLite des liens offre ↔ recherche (crée et migre sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        is_new = not _table_exists(conn, _TABLE)
        self.conn.execute(_CREATE_TABLE)
        if is_new:
            self._link_existing_offers()
        self.conn.commit()

    def _link_existing_offers(self) -> None:
        """Rattache chaque offre existante à chaque recherche existante (migration OPP-186).

        Ne tourne qu'à la création de la table : une base neuve (ni offre ni recherche) ne lie
        rien, et une recherche créée plus tard part sans offre.
        """
        if not (_table_exists(self.conn, "offers") and _table_exists(self.conn, "candidates")):
            return
        self.conn.execute(
            f"INSERT OR IGNORE INTO {_TABLE} (candidate_id, offer_id, created_at) "
            "SELECT c.id, o.id, o.created_at FROM candidates AS c CROSS JOIN offers AS o"
        )

    def link(self, candidate_id: str, offer_id: str) -> None:
        """Rattache l'offre à la recherche. Idempotent : un lien existant garde sa date."""
        self.conn.execute(
            f"INSERT OR IGNORE INTO {_TABLE} (candidate_id, offer_id, created_at) "
            "VALUES (?, ?, ?)",
            (candidate_id, offer_id, _utcnow_iso()),
        )
        self.conn.commit()

    def is_linked(self, candidate_id: str, offer_id: str) -> bool:
        """L'offre est-elle déjà visible pour cette recherche ?"""
        row = self.conn.execute(
            f"SELECT 1 FROM {_TABLE} WHERE candidate_id = ? AND offer_id = ?",
            (candidate_id, offer_id),
        ).fetchone()
        return row is not None

    def links(
        self, candidate_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[tuple[str, str]]:
        """``(offer_id, date d'entrée)`` de la recherche, entrées les plus récentes d'abord.

        ``limit``/``offset`` paginent ; ``limit=None`` rend tout.
        """
        if limit is None:
            rows = self.conn.execute(_SELECT_LINKS, (candidate_id,)).fetchall()
        else:
            rows = self.conn.execute(
                _SELECT_LINKS + " LIMIT ? OFFSET ?", (candidate_id, limit, offset)
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def offer_ids(
        self, candidate_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[str]:
        """Ids des offres de la recherche, dans l'ordre de ``links``."""
        return [offer_id for offer_id, _ in self.links(candidate_id, limit=limit, offset=offset)]

    def count(self, candidate_id: str) -> int:
        """Nombre d'offres de la recherche (liens vers une offre absente non comptés)."""
        return self.conn.execute(
            f"SELECT COUNT(*) FROM {_TABLE} AS l JOIN offers AS o ON o.id = l.offer_id "
            "WHERE l.candidate_id = ?",
            (candidate_id,),
        ).fetchone()[0]
