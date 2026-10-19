"""Persistance des offres en SQLite (V2, OPP-037).

``OfferStore`` enregistre et met à jour des ``Offer`` dans une base SQLite (via
``app.db``). L'écriture est un **upsert** sur l'``id`` stable : ré-enregistrer la même
offre met à jour la ligne existante au lieu de la dupliquer. Les champs liste
(``skills``, ``attention_points``) sont sérialisés en JSON.

Le métier dépend du protocole ``OfferRepository`` (et non de SQLite directement), ce
qui permet d'injecter une fausse persistance en test.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from app.offer import Offer, compute_offer_id
from app.offer_kind import DEFAULT_KIND, FORMATION, classify_kind

_COLUMNS = (
    "id",
    "title",
    "company",
    "location",
    "skills",
    "seniority",
    "contract_type",
    "summary",
    "attention_points",
    "source",
    "url",
    "raw_text",
    "kind",
    "created_at",
)

# Colonnes préservées à l'upsert (jamais réécrites par un ré-enregistrement) : l'``id``
# (clé de conflit) et ``created_at``, la date de **première** ingestion — recoller ou
# re-scorer une offre ne la fait donc pas remonter en tête (OPP-152).
_PRESERVED_ON_UPSERT = ("id", "created_at")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    skills TEXT NOT NULL,
    seniority TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    attention_points TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'emploi',
    created_at TEXT NOT NULL DEFAULT ''
)
"""


def _utcnow_iso() -> str:
    """Horodatage d'ingestion : instant courant UTC en ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


@runtime_checkable
class OfferRepository(Protocol):
    """Contrat de persistance d'offres consommé par le métier."""

    def save(self, offer: Offer) -> None: ...

    def get(self, offer_id: str) -> Offer | None: ...


class OfferStore:
    """Dépôt SQLite d'offres (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # ``get`` accède aux colonnes par nom : on garantit le factory ici plutôt
        # que de dépendre de la configuration de la connexion injectée.
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self._migrate_created_at()
        self._migrate_offer_ids()
        self._migrate_kind()
        self.conn.commit()

    def _migrate_created_at(self) -> None:
        """Ajoute ``created_at`` aux bases antérieures à OPP-152 et date les offres existantes.

        SQLite interdit un défaut non constant (``CURRENT_TIMESTAMP``) sur un ``ALTER TABLE
        ADD COLUMN`` : on ajoute donc la colonne avec un défaut vide, puis on **backfill** les
        lignes pré-existantes à l'instant de migration (faute de date d'ingestion connue).
        """
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(offers)")}
        if "created_at" in existing:
            return
        self.conn.execute("ALTER TABLE offers ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
        self.conn.execute(
            "UPDATE offers SET created_at = ? WHERE created_at = ''", (_utcnow_iso(),)
        )

    def _migrate_offer_ids(self) -> None:
        """Recale les id sur le schéma d'identité courant (canonicalisation d'URL, OPP-119).

        Les offres ingérées avant OPP-119 portent un id dérivé d'un schéma plus ancien
        (URL minusculée *en entier*, slash final / ``utm_*`` / port par défaut conservés).
        On recalcule l'id déterministe de chaque ligne à partir de ses ``source``/``url``/
        ``raw_text`` stockés ; s'il a changé, on réécrit la clé. Deux liens qui
        canonicalisent désormais vers le même id (« même offre, deux liens ») sont
        **fusionnés** : la ligne la plus anciennement ingérée (``created_at``) fait foi.

        Idempotent : une base déjà au schéma courant ne bouge pas (l'id recalculé est
        identique), donc ré-exécuter à chaque ouverture est sans effet.
        """
        rows = self.conn.execute(
            "SELECT id, source, url, raw_text, created_at FROM offers"
        ).fetchall()
        for row in rows:
            new_id = compute_offer_id(row["source"], row["url"], row["raw_text"])
            if new_id == row["id"]:
                continue
            existing = self.conn.execute(
                "SELECT created_at FROM offers WHERE id = ?", (new_id,)
            ).fetchone()
            if existing is None:
                self.conn.execute(
                    "UPDATE offers SET id = ? WHERE id = ?", (new_id, row["id"])
                )
            elif (row["created_at"] or "") < (existing["created_at"] or ""):
                # Collision : la ligne courante est la plus ancienne → elle remplace
                # celle déjà sous le nouvel id.
                self.conn.execute("DELETE FROM offers WHERE id = ?", (new_id,))
                self.conn.execute(
                    "UPDATE offers SET id = ? WHERE id = ?", (new_id, row["id"])
                )
            else:
                # La ligne déjà présente sous le nouvel id est au moins aussi ancienne :
                # on écarte le doublon courant.
                self.conn.execute("DELETE FROM offers WHERE id = ?", (row["id"],))

    def _migrate_kind(self) -> None:
        """Ajoute ``kind`` aux bases antérieures à OPP-166 et re-type les offres existantes.

        Deux temps : (1) si la colonne manque, on l'ajoute avec le défaut ``emploi`` (les
        offres pré-OPP-166 étaient toutes traitées comme des emplois) ; (2) on **promeut** en
        ``formation`` les lignes dont le titre/texte porte des marqueurs explicites
        (``classify_kind``), ce qui re-type d'un coup la base existante (ex. la POE ISTQB).

        La promotion ne **déclasse jamais** une formation en emploi : une formation détectée
        par le LLM à l'intake mais sans marqueur heuristique reste une formation. Idempotent
        (ne touche que les ``emploi`` à promouvoir), donc ré-exécuter à chaque ouverture est
        sans effet une fois la base à jour.
        """
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(offers)")}
        if "kind" not in existing:
            self.conn.execute(
                f"ALTER TABLE offers ADD COLUMN kind TEXT NOT NULL DEFAULT '{DEFAULT_KIND}'"
            )
        rows = self.conn.execute(
            "SELECT id, title, raw_text FROM offers WHERE kind != ?", (FORMATION,)
        ).fetchall()
        for row in rows:
            if classify_kind(row["title"], row["raw_text"]) == FORMATION:
                self.conn.execute(
                    "UPDATE offers SET kind = ? WHERE id = ?", (FORMATION, row["id"])
                )

    def save(self, offer: Offer) -> None:
        """Insère l'offre ou met à jour la ligne existante (upsert sur ``id``).

        ``created_at`` est posé **à l'insertion** et préservé à l'upsert (cf.
        ``_PRESERVED_ON_UPSERT``) : la date reflète la première ingestion, pas la dernière.
        """
        _JSON_COLUMNS = ("skills", "attention_points")
        values = {
            **{col: getattr(offer, col) for col in _COLUMNS if col not in _JSON_COLUMNS},
            "skills": json.dumps(offer.skills, ensure_ascii=False),
            "attention_points": json.dumps(offer.attention_points, ensure_ascii=False),
            # Une offre fraîche (``created_at`` vide, cas nominal via ``from_analysis``) est
            # horodatée maintenant ; l'upsert ci-dessous ne touche jamais cette colonne.
            "created_at": offer.created_at or _utcnow_iso(),
        }
        placeholders = ", ".join(f":{col}" for col in _COLUMNS)
        updates = ", ".join(
            f"{col} = excluded.{col}" for col in _COLUMNS if col not in _PRESERVED_ON_UPSERT
        )
        self.conn.execute(
            f"INSERT INTO offers ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )
        self.conn.commit()

    @staticmethod
    def _row_to_offer(row: sqlite3.Row) -> Offer:
        """Reconstruit une ``Offer`` depuis une ligne SQLite (désérialise les champs JSON)."""
        return Offer(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            skills=json.loads(row["skills"]),
            seniority=row["seniority"],
            contract_type=row["contract_type"],
            summary=row["summary"],
            attention_points=json.loads(row["attention_points"]),
            source=row["source"],
            url=row["url"],
            raw_text=row["raw_text"],
            kind=row["kind"],
            created_at=row["created_at"],
        )

    def get(self, offer_id: str) -> Offer | None:
        """Retourne l'offre d'``id`` donné, ou ``None`` si absente."""
        row = self.conn.execute(
            "SELECT * FROM offers WHERE id = ?", (offer_id,)
        ).fetchone()
        return None if row is None else self._row_to_offer(row)

    def list_all(self) -> list[Offer]:
        """Retourne toutes les offres, **plus récentes d'abord** (OPP-152).

        Tri par date d'ingestion décroissante ; ``id`` en tie-break pour un ordre
        déterministe (dates égales, p. ex. offres backfillées à la migration).
        """
        rows = self.conn.execute(
            "SELECT * FROM offers ORDER BY created_at DESC, id"
        ).fetchall()
        return [self._row_to_offer(row) for row in rows]

    def list(self, *, limit: int, offset: int = 0) -> list[Offer]:
        """Page d'offres, **plus récentes d'abord** (catalogue paginé, OPP-146).

        Même ordre que ``list_all`` (``created_at DESC, id``) ; ``limit``/``offset``
        découpent la page. ``count`` donne le cardinal total pour la pagination.
        """
        rows = self.conn.execute(
            "SELECT * FROM offers ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_offer(row) for row in rows]

    def count(self) -> int:
        """Nombre d'offres stockées (utile aux vérifications d'upsert)."""
        return self.conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
