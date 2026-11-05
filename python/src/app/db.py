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

from app.paths import user_data_dir

# Chemin de la base par défaut, surchargeable via la variable d'environnement
# OPPORTUNE_DB_PATH (ex. dans docker-compose). ":memory:" est accepté (tests).
# À défaut d'override, le dossier dépend du contexte (dev vs binaire gelé) : voir
# ``app.paths.user_data_dir``. En mode packagé, ``data/`` relatif n'existe pas et
# n'est pas inscriptible — la base est routée vers un répertoire par utilisateur.
DEFAULT_DB_PATH = os.environ.get("OPPORTUNE_DB_PATH") or str(
    user_data_dir() / "opportune.db"
)


# Attente max (ms) sur un verrou SQLite avant d'abandonner (``PRAGMA busy_timeout``).
# Par défaut SQLite échoue **immédiatement** (``database is locked``) si la base est
# verrouillée. La collecte asynchrone (OPP-170) fait coexister deux connexions sur le
# même fichier — le thread du job qui écrit et le thread HTTP qui lit (sondage / catalogue).
# Couplé au mode WAL, ce délai laisse une écriture ponctuelle se terminer au lieu de faire
# échouer la lecture concurrente.
_BUSY_TIMEOUT_MS = 5000


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite configurée.

    - ``db_path=None`` → :data:`DEFAULT_DB_PATH` ; ``":memory:"`` ouvre une base en
      mémoire (pratique pour les tests) ;
    - crée le dossier parent au besoin (bases sur fichier) ;
    - lignes accessibles par nom (``sqlite3.Row``) ;
    - contraintes de clés étrangères activées (``PRAGMA foreign_keys = ON``) ;
    - **mode WAL** + ``busy_timeout`` (bases sur fichier) pour tolérer un lecteur et un
      écrivain concurrents sur le même fichier — requis par la collecte asynchrone
      (OPP-170), où le job de fond écrit pendant que l'API lit. WAL est une propriété
      persistante du fichier et sans objet pour ``":memory:"`` (laissé en mode mémoire).
    """
    path = db_path or DEFAULT_DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    return conn


def database_path(conn: sqlite3.Connection) -> str | None:
    """Chemin du fichier de la base ``main`` d'une connexion, ou ``None`` si en mémoire/temp.

    Sert à ouvrir une **seconde** connexion sur la MÊME base que ``conn`` (collecte asynchrone,
    OPP-170 : le thread du job a sa propre connexion). SQLite expose le chemin via
    ``PRAGMA database_list`` ; il est vide pour une base en mémoire ou temporaire — on rend
    alors ``None`` (le fichier n'est pas partageable entre connexions, seul le cas sur fichier
    de la prod l'est).
    """
    for _seq, name, file in conn.execute("PRAGMA database_list"):
        if name == "main":
            return file or None
    return None


def healthcheck(conn: sqlite3.Connection) -> bool:
    """Vrai si la base répond à une requête triviale (``SELECT 1``)."""
    return conn.execute("SELECT 1").fetchone()[0] == 1
