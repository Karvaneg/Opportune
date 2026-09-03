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
from typing import Protocol, runtime_checkable

from app.offer import Offer

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
)

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
    raw_text TEXT NOT NULL
)
"""


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
        self.conn.commit()

    def save(self, offer: Offer) -> None:
        """Insère l'offre ou met à jour la ligne existante (upsert sur ``id``)."""
        _JSON_COLUMNS = ("skills", "attention_points")
        values = {
            **{col: getattr(offer, col) for col in _COLUMNS if col not in _JSON_COLUMNS},
            "skills": json.dumps(offer.skills, ensure_ascii=False),
            "attention_points": json.dumps(offer.attention_points, ensure_ascii=False),
        }
        placeholders = ", ".join(f":{col}" for col in _COLUMNS)
        updates = ", ".join(f"{col} = excluded.{col}" for col in _COLUMNS if col != "id")
        self.conn.execute(
            f"INSERT INTO offers ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )
        self.conn.commit()

    def get(self, offer_id: str) -> Offer | None:
        """Retourne l'offre d'``id`` donné, ou ``None`` si absente."""
        row = self.conn.execute(
            "SELECT * FROM offers WHERE id = ?", (offer_id,)
        ).fetchone()
        if row is None:
            return None
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
        )

    def count(self) -> int:
        """Nombre d'offres stockées (utile aux vérifications d'upsert)."""
        return self.conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
