"""Configuration et accès SQLite (V2, OPP-072).

Connexion à une base SQLite via la bibliothèque standard (``sqlite3``) — aucune
dépendance externe, aucun ORM (SQLAlchemy viendra plus tard). Ce module fournit le
chemin de base par défaut (surchargeable par variable d'environnement) et un
constructeur de connexion configuré. Aucun schéma métier n'est encore défini : c'est
la configuration de l'accès, pas la migration des modèles.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Chemin de la base par défaut, surchargeable via la variable d'environnement
# OPPORTUNE_DB_PATH (ex. dans docker-compose). ":memory:" est accepté (tests).
DEFAULT_DB_PATH = os.environ.get("OPPORTUNE_DB_PATH", "data/opportune.db")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite configurée.

    - ``db_path=None`` → :data:`DEFAULT_DB_PATH` ; ``":memory:"`` ouvre une base en
      mémoire (pratique pour les tests) ;
    - crée le dossier parent au besoin (bases sur fichier) ;
    - lignes accessibles par nom (``sqlite3.Row``) ;
    - contraintes de clés étrangères activées (``PRAGMA foreign_keys = ON``).
    """
    path = db_path or DEFAULT_DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def healthcheck(conn: sqlite3.Connection) -> bool:
    """Vrai si la base répond à une requête triviale (``SELECT 1``)."""
    return conn.execute("SELECT 1").fetchone()[0] == 1
