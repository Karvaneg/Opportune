"""Résolution du répertoire de données inscriptible (OPP-190).

En développement, les bases SQLite vivent dans ``data/`` relatif au dossier de
travail — comportement historique, inchangé. Empaquetée avec PyInstaller,
l'application tourne depuis un binaire en lecture seule lancé depuis un dossier
arbitraire : ``data/`` n'existe pas et n'est pas inscriptible. On route alors
les bases vers un répertoire **par utilisateur**, propre à chaque OS.

Priorités (de la plus forte à la plus faible) :

1. ``OPPORTUNE_DATA_DIR`` — force l'emplacement dans tous les cas (tests,
   installation personnalisée) ;
2. binaire gelé (``sys.frozen``) → répertoire de données par OS ;
3. défaut historique → ``data/`` relatif.

Ce module ne crée aucun dossier : il calcule un chemin. La création est faite
par ``app.db.connect`` (``mkdir(parents=True)``) au moment d'ouvrir la base.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Nom du sous-dossier applicatif dans l'espace de données de l'utilisateur.
# Capitalisé sur Windows/macOS (convention de ces plateformes), en minuscules
# sous Linux (convention XDG, ex. ~/.local/share/opportune).
_APP_DIR_NAME = "Opportune"


def user_data_dir() -> Path:
    """Répertoire où ranger les bases SQLite, selon le contexte d'exécution."""
    override = os.environ.get("OPPORTUNE_DATA_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return _frozen_data_dir()
    return Path("data")


def _frozen_data_dir() -> Path:
    """Répertoire de données par utilisateur, selon l'OS (mode binaire gelé)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / _APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / _APP_DIR_NAME.lower()
