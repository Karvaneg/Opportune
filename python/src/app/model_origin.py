"""Trace de l'origine du modèle LLM : téléchargé par Opportune, ou déjà présent ? (OPP-251)

Opportune réutilise autant que possible l'Ollama et les modèles déjà installés sur la machine.
Un modèle peut donc se trouver dans le dossier Ollama **de la personne** sans qu'Opportune l'y
ait mis. Pour qu'une désinstallation (OPP-252) ne supprime jamais un modèle qui existait avant
l'app, on note ici, dans un petit fichier JSON du dossier de données, chaque téléchargement fait
par Opportune : le **nom du modèle**, le **dossier de modèles** où il a atterri et une
**empreinte** de la copie (date de modification donnée par Ollama).

Le dossier compte autant que le nom : un même modèle peut exister en deux copies (une
téléchargée par Opportune dans son dossier, une autre que la personne a téléchargée ensuite dans
son ``~/.ollama``). Seule la copie du dossier noté vient d'Opportune.

Le dossier vaut ``None`` quand Opportune a téléchargé le modèle **à travers l'Ollama de la
personne** : cet Ollama range ses modèles selon sa propre configuration, que l'app ne connaît pas.
C'est là que l'empreinte sert : si la personne supprime ce modèle puis le retélécharge pour son
propre usage, la date change, et la nouvelle copie n'est plus tenue pour celle d'Opportune.

Un téléchargement absent du fichier est considéré comme **déjà présent** : c'est le choix sans
risque, il conduit à ne rien supprimer. C'est aussi le cas des modèles téléchargés par une
version d'Opportune antérieure à ce suivi.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Nom du fichier de trace, rangé dans le dossier de données de l'app (cf. ``app.paths``).
MODEL_ORIGIN_FILENAME = "llm-model-origin.json"

# Variable posée par la coquille de bureau (``main.rs``) : dossier de modèles de l'Ollama
# qu'elle a lancé. Absente quand l'app réutilise l'Ollama de la personne, ou hors app de bureau.
MODELS_DIR_ENV = "OPPORTUNE_OLLAMA_MODELS_DIR"

_DOWNLOADS_KEY = "downloaded_by_opportune"


def models_dir_from_env(environ: dict[str, str] | None = None) -> str | None:
    """Dossier de modèles de l'Ollama lancé par l'app, ou ``None`` s'il n'est pas connu."""
    value = (environ if environ is not None else os.environ).get(MODELS_DIR_ENV, "").strip()
    return value or None


class ModelOriginStore:
    """Liste, sur disque, des modèles téléchargés par Opportune, de leur dossier et de leur
    empreinte."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def mark_downloaded(
        self, model: str, models_dir: str | None, fingerprint: str | None = None
    ) -> None:
        """Note que ``model`` a été téléchargé par Opportune dans ``models_dir``.

        ``fingerprint`` identifie cette copie précise (date de modification donnée par Ollama).
        Un nouveau téléchargement du même modèle au même endroit remplace l'entrée précédente.
        """
        downloads = [entry for entry in self._read() if not _matches(entry, model, models_dir)]
        downloads.append({"model": model, "models_dir": models_dir, "fingerprint": fingerprint})
        self._write(downloads)

    def forget(self, model: str, models_dir: str | None) -> None:
        """Retire la trace d'un téléchargement (la copie vient d'être supprimée)."""
        downloads = self._read()
        remaining = [entry for entry in downloads if not _matches(entry, model, models_dir)]
        if len(remaining) != len(downloads):
            self._write(remaining)

    def was_downloaded_by_opportune(self, model: str, models_dir: str | None) -> bool:
        """Vrai si Opportune a téléchargé ``model`` dans ``models_dir``."""
        return any(_matches(entry, model, models_dir) for entry in self._read())

    def fingerprint_of(self, model: str, models_dir: str | None) -> str | None:
        """Empreinte notée au téléchargement de ``model`` dans ``models_dir`` ; ``None`` si
        Opportune ne l'y a pas téléchargé, ou sans empreinte connue."""
        for entry in self._read():
            if _matches(entry, model, models_dir):
                return entry["fingerprint"]
        return None

    def _write(self, downloads: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({_DOWNLOADS_KEY: downloads}, indent=2), encoding="utf-8")

    def _read(self) -> list[dict]:
        """Téléchargements notés. Fichier absent ou illisible → liste vide (rien n'est tenu
        pour téléchargé par Opportune). Les entrées mal formées sont ignorées."""
        try:
            content = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        downloads = content.get(_DOWNLOADS_KEY) if isinstance(content, dict) else None
        if not isinstance(downloads, list):
            return []
        return [
            {
                "model": entry["model"],
                "models_dir": entry.get("models_dir"),
                "fingerprint": entry.get("fingerprint"),
            }
            for entry in downloads
            if isinstance(entry, dict)
            and isinstance(entry.get("model"), str)
            and isinstance(entry.get("models_dir"), (str, type(None)))
            and isinstance(entry.get("fingerprint"), (str, type(None)))
        ]


def _matches(entry: dict, model: str, models_dir: str | None) -> bool:
    return entry["model"] == model and entry["models_dir"] == models_dir
