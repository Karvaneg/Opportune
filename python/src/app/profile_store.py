"""Persistance des profils candidats en SQLite (V2, OPP-017).

``ProfileStore`` enregistre et met à jour des ``CandidateProfile`` (via ``app.db``).
L'écriture est un **upsert** sur l'``id`` : ré-enregistrer le même profil met à jour la
ligne au lieu de la dupliquer. Les champs liste/structurés sont sérialisés en JSON.

Le métier dépend du protocole ``ProfileRepository`` (et non de SQLite directement),
d'où l'injection possible d'une fausse persistance en test.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Protocol, runtime_checkable

from app.candidate_profile import CandidateProfile

# Colonnes stockées en JSON (listes / structures).
_JSON_COLUMNS = ("skills", "structured_skills", "experiences", "languages", "constraints")

# Ordre des colonnes de la table (= attributs de CandidateProfile).
_COLUMNS = (
    "id",
    "name",
    "skills",
    "contract_type",
    "structured_skills",
    "experiences",
    "total_experience_years",
    "location",
    "mobility",
    "remote",
    "target_salary",
    "target_daily_rate",
    "languages",
    "availability",
    "constraints",
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    skills TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    structured_skills TEXT NOT NULL,
    experiences TEXT NOT NULL,
    total_experience_years REAL,
    location TEXT,
    mobility TEXT,
    remote TEXT,
    target_salary REAL,
    target_daily_rate REAL,
    languages TEXT NOT NULL,
    availability TEXT,
    constraints TEXT NOT NULL
)
"""


@runtime_checkable
class ProfileRepository(Protocol):
    """Contrat de persistance de profils consommé par le métier."""

    def save(self, profile: CandidateProfile) -> None: ...

    def get(self, profile_id: str) -> CandidateProfile | None: ...


class ProfileStore:
    """Dépôt SQLite de profils candidats (crée sa table au besoin)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        # ``get`` accède aux colonnes par nom : on garantit le factory ici.
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(_CREATE_TABLE)
        self.conn.commit()

    def save(self, profile: CandidateProfile) -> None:
        """Insère le profil ou met à jour la ligne existante (upsert sur ``id``)."""
        values = {
            col: (
                json.dumps(getattr(profile, col), ensure_ascii=False)
                if col in _JSON_COLUMNS
                else getattr(profile, col)
            )
            for col in _COLUMNS
        }
        placeholders = ", ".join(f":{col}" for col in _COLUMNS)
        updates = ", ".join(f"{col} = excluded.{col}" for col in _COLUMNS if col != "id")
        self.conn.execute(
            f"INSERT INTO profiles ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )
        self.conn.commit()

    def get(self, profile_id: str) -> CandidateProfile | None:
        """Retourne le profil d'``id`` donné, ou ``None`` si absent."""
        row = self.conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if row is None:
            return None
        data = {col: row[col] for col in _COLUMNS}
        for col in _JSON_COLUMNS:
            data[col] = json.loads(data[col])
        return CandidateProfile(**data)

    def count(self) -> int:
        """Nombre de profils stockés."""
        return self.conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
