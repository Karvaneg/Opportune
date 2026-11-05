"""Export et import des données d'un espace (OPP-232).

Assemble les briques pour l'API :

- **export** : construit l'archive (``app.data_archive``) et la rend avec un nom de fichier daté.
  L'API n'écrit rien sur le disque : c'est le front qui enregistre le fichier à l'endroit choisi
  par l'utilisateur (fenêtre « Enregistrer sous ») ;
- **import** : refuse pendant une collecte en cours (elle écrit dans la base), puis remplace la
  base et les réglages par le contenu de l'archive. ``is_busy`` doit couvrir **toute** tâche de
  fond qui écrit dans la base de l'espace ; aujourd'hui seule la collecte le fait (la mise en
  place du LLM, l'autre tâche de fond, n'écrit que hors base).

Un service par espace : « Mon espace » et la Démo ont chacun leur base et leurs réglages.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from app.data_archive import build_archive, restore_archive

# Taille max d'une archive importée : une base de plusieurs années tient largement dedans.
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024


class ExportTooLarge(Exception):
    """L'archive dépasse la taille qu'un import accepte : elle ne pourrait pas être réimportée."""


class DataTransferBusy(Exception):
    """Une collecte est en cours : l'import attendrait la fin de ses écritures."""


@dataclass(frozen=True)
class ExportResult:
    """Archive d'export et nom de fichier proposé à l'enregistrement."""

    content: bytes
    filename: str


class DataTransferService:
    """Export / import des données d'un espace (base SQLite + fichiers de réglages)."""

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        settings_files: Sequence[Path],
        app_version: str,
        ensure_schema: Callable[[sqlite3.Connection], None],
        is_busy: Callable[[], bool] = lambda: False,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._conn = conn
        self._settings_files = list(settings_files)
        self._app_version = app_version
        self._ensure_schema = ensure_schema
        self._is_busy = is_busy
        self._now = now

    def export(self) -> ExportResult:
        """Construit l'archive ; rend son contenu et un nom daté (ex. ``opportune-export-2026-11-05.zip``)."""
        now = self._now()
        content = build_archive(
            self._conn,
            self._settings_files,
            app_version=self._app_version,
            exported_at=now.isoformat(timespec="seconds"),
        )
        # Un export que l'import refuserait est inutile : on le dit tout de suite plutôt que de
        # le découvrir sur le nouvel ordinateur.
        if len(content) > MAX_ARCHIVE_BYTES:
            raise ExportTooLarge(
                "les données dépassent la taille maximale d'un export (200 Mo) : "
                "l'archive ne pourrait pas être réimportée"
            )
        return ExportResult(content=content, filename=f"opportune-export-{now:%Y-%m-%d}.zip")

    def import_(self, data: bytes) -> None:
        """Remplace les données de l'espace par celles de l'archive (tout ou rien)."""
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("le fichier dépasse la taille maximale d'un export (200 Mo)")
        if self._is_busy():
            raise DataTransferBusy(
                "une collecte d'offres est en cours : attends sa fin ou arrête-la, puis réessaie"
            )
        restore_archive(
            data,
            self._conn,
            self._settings_files,
            app_version=self._app_version,
            ensure_schema=self._ensure_schema,
        )
