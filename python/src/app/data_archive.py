"""Archive d'export des données d'un espace : construction et restauration (OPP-232).

Une archive est un fichier ``.zip`` qui contient :

- ``manifest.json`` : format, version du format et version d'Opportune qui l'a produite ;
- ``opportune.db`` : copie cohérente de la base SQLite (API de sauvegarde SQLite, valable même
  pendant que l'app écrit) ;
- ``settings/<nom>`` : les fichiers de réglages présents (clés Adzuna, flux RSS, entreprises
  ciblées). Les clés Adzuna sont incluses : l'utilisatrice en est prévenue à l'export.

La restauration **remplace tout** : la base est recopiée dans la connexion ouverte (API de
sauvegarde SQLite, en sens inverse) et chaque fichier de réglages est réécrit, ou supprimé s'il
est absent de l'archive. Tout est vérifié **avant** la moindre écriture : une archive invalide,
corrompue ou produite par une version plus récente d'Opportune est refusée sans rien modifier.
Si une écriture échoue en cours de route (disque plein, dossier en lecture seule), la base et
les réglages d'avant sont remis en place : l'import est **tout ou rien**.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, Sequence

ARCHIVE_FORMAT = "opportune-export"
FORMAT_VERSION = 1
_MANIFEST = "manifest.json"
_DATABASE = "opportune.db"
_SETTINGS_PREFIX = "settings/"
# Tailles max **décompressées** : la limite de taille de l'archive porte sur le ``.zip``
# compressé ; sans ces bornes, un zip très compressible gonflerait à plusieurs Go en lecture.
MAX_DATABASE_BYTES = 2 * 1024 * 1024 * 1024
MAX_SETTINGS_FILE_BYTES = 1024 * 1024
_MANIFEST_MAX_BYTES = 64 * 1024


class DataArchiveError(ValueError):
    """Archive refusée : illisible, incomplète, corrompue ou d'une version incompatible."""


def _version_tuple(version: str) -> tuple[int, ...]:
    """Partie numérique d'une version : ``1.1.0rc1`` et ``1.0.0-dev`` → ``(1, 1, 0)``, ``(1, 0, 0)``.

    Le suffixe de pré-version est ignoré : une build de développement ne doit pas faire échouer
    tous les imports.
    """
    parts = []
    for part in version.split("."):
        match = re.match(r"\d+", part)
        if match is None:
            break
        parts.append(int(match.group()))
        if match.end() != len(part):
            break
    if not parts:
        raise DataArchiveError(f"version d'Opportune illisible dans l'archive : {version}")
    return tuple(parts)


def _read_bounded(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    """Lit une entrée de l'archive en refusant toute taille décompressée au-delà de ``limit``."""
    if archive.getinfo(name).file_size > limit:
        raise DataArchiveError("l'export est refusé (contenu décompressé trop volumineux)")
    return archive.read(name)


def build_archive(
    conn: sqlite3.Connection,
    settings_files: Sequence[Path],
    *,
    app_version: str,
    exported_at: str,
) -> bytes:
    """Construit l'archive (octets du ``.zip``) de la base et des réglages présents."""
    with tempfile.TemporaryDirectory() as tmp:
        snapshot_path = Path(tmp) / _DATABASE
        snapshot = sqlite3.connect(snapshot_path)
        try:
            conn.backup(snapshot)
        finally:
            snapshot.close()
        manifest = {
            "format": ARCHIVE_FORMAT,
            "format_version": FORMAT_VERSION,
            "app_version": app_version,
            "exported_at": exported_at,
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(_MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.write(snapshot_path, _DATABASE)
            for path in settings_files:
                if path.is_file():
                    archive.write(path, _SETTINGS_PREFIX + path.name)
        return buffer.getvalue()


def _read_manifest(archive: zipfile.ZipFile, app_version: str) -> None:
    try:
        manifest = json.loads(_read_bounded(archive, _MANIFEST, _MANIFEST_MAX_BYTES))
    except KeyError as exc:
        raise DataArchiveError("ce fichier n'est pas un export d'Opportune") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DataArchiveError("l'export est endommagé (manifeste illisible)") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT:
        raise DataArchiveError("ce fichier n'est pas un export d'Opportune")
    format_version = manifest.get("format_version")
    if not isinstance(format_version, int) or format_version > FORMAT_VERSION:
        raise DataArchiveError(
            "cet export vient d'une version plus récente d'Opportune : mets l'app à jour"
        )
    exported_with = manifest.get("app_version")
    if not isinstance(exported_with, str):
        raise DataArchiveError("l'export est endommagé (version d'Opportune absente)")
    if _version_tuple(exported_with) > _version_tuple(app_version):
        raise DataArchiveError(
            f"cet export vient d'Opportune {exported_with}, plus récent que cette app "
            f"({app_version}) : mets l'app à jour"
        )


def _check_database(path: Path) -> None:
    try:
        candidate = sqlite3.connect(path)
        try:
            result = candidate.execute("PRAGMA integrity_check").fetchone()
        finally:
            candidate.close()
    except sqlite3.DatabaseError as exc:
        raise DataArchiveError("l'export est endommagé (base illisible)") from exc
    if result is None or result[0] != "ok":
        raise DataArchiveError("l'export est endommagé (base corrompue)")


def _write_private(path: Path, content: bytes) -> None:
    """Écrit un fichier de réglages lisible par son seul propriétaire (il peut porter un secret).

    Écriture dans un fichier voisin puis renommage : le fichier n'est jamais à moitié écrit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _apply_settings(settings: dict[Path, bytes | None]) -> None:
    for path, content in settings.items():
        if content is None:
            path.unlink(missing_ok=True)
        else:
            _write_private(path, content)


def _copy_database(source_path: Path, conn: sqlite3.Connection) -> None:
    source = sqlite3.connect(source_path)
    try:
        source.backup(conn)
    finally:
        source.close()


def restore_archive(
    data: bytes,
    conn: sqlite3.Connection,
    settings_files: Sequence[Path],
    *,
    app_version: str,
    ensure_schema: Callable[[sqlite3.Connection], None],
) -> None:
    """Remplace la base de ``conn`` et les réglages par le contenu de l'archive (tout ou rien)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DataArchiveError("ce fichier n'est pas un export d'Opportune") from exc
    with archive, tempfile.TemporaryDirectory() as tmp:
        _read_manifest(archive, app_version)
        database_path = Path(tmp) / _DATABASE
        try:
            if archive.getinfo(_DATABASE).file_size > MAX_DATABASE_BYTES:
                raise DataArchiveError("l'export est refusé (base décompressée trop volumineuse)")
            # Copie en flux vers le disque : la base n'est jamais entièrement en mémoire.
            with archive.open(_DATABASE) as src, database_path.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            names = set(archive.namelist())
            settings = {
                path: (
                    _read_bounded(archive, _SETTINGS_PREFIX + path.name, MAX_SETTINGS_FILE_BYTES)
                    if _SETTINGS_PREFIX + path.name in names
                    else None
                )
                for path in settings_files
            }
        except KeyError as exc:
            raise DataArchiveError("l'export est incomplet (base absente)") from exc
        except (zipfile.BadZipFile, OSError) as exc:
            raise DataArchiveError("l'export est endommagé") from exc
        _check_database(database_path)

        # Sauvegarde de l'état actuel, pour le remettre en place si une écriture échoue.
        previous_database = Path(tmp) / "previous.db"
        backup = sqlite3.connect(previous_database)
        try:
            conn.backup(backup)
        finally:
            backup.close()
        previous_settings = {
            path: path.read_bytes() if path.is_file() else None for path in settings_files
        }

        try:
            _copy_database(database_path, conn)
            ensure_schema(conn)
            _apply_settings(settings)
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            _copy_database(previous_database, conn)
            _apply_settings(previous_settings)
            raise
