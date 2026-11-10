"""Trace de l'origine du modèle LLM : téléchargé par Opportune, ou déjà présent ? (OPP-251)

Opportune réutilise autant que possible l'Ollama et les modèles déjà installés sur la machine.
Un modèle peut donc se trouver dans le dossier Ollama **de la personne** sans qu'Opportune l'y
ait mis. Pour qu'une désinstallation (OPP-252) ne supprime jamais un modèle qui existait avant
l'app, on note ici, dans un petit fichier JSON du dossier de données, chaque téléchargement fait
par Opportune : le **nom du modèle** et le **dossier de modèles** où il a atterri.

Le dossier compte autant que le nom : un même modèle peut exister en deux copies (une
téléchargée par Opportune dans son dossier, une autre que la personne a téléchargée ensuite dans
son ``~/.ollama``). Seule la copie du dossier noté vient d'Opportune.

Le dossier vaut ``None`` quand Opportune a téléchargé le modèle **à travers l'Ollama de la
personne** : cet Ollama range ses modèles selon sa propre configuration, que l'app ne connaît pas.

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
    """Liste, sur disque, des modèles téléchargés par Opportune et de leur dossier."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def mark_downloaded(self, model: str, models_dir: str | None) -> None:
        """Note que ``model`` a été téléchargé par Opportune dans ``models_dir`` (sans doublon)."""
        downloads = self._read()
        entry = {"model": model, "models_dir": models_dir}
        if entry in downloads:
            return
        downloads.append(entry)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({_DOWNLOADS_KEY: downloads}, indent=2), encoding="utf-8")

    def was_downloaded_by_opportune(self, model: str, models_dir: str | None) -> bool:
        """Vrai si la copie de ``model`` située dans ``models_dir`` vient d'Opportune."""
        return {"model": model, "models_dir": models_dir} in self._read()

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
            {"model": entry["model"], "models_dir": entry.get("models_dir")}
            for entry in downloads
            if isinstance(entry, dict)
            and isinstance(entry.get("model"), str)
            and isinstance(entry.get("models_dir"), (str, type(None)))
        ]
