"""Désinstallation d'Opportune depuis l'app (OPP-252).

Objectif : quand la personne désinstalle Opportune, lui permettre de récupérer la place occupée
(le modèle LLM pèse environ 3 Go) et lui dire clairement ce qui reste sur sa machine.

Partage des rôles avec la coquille de bureau (``frontend/src-tauri/src/main.rs``) :

- ce service **décrit** la situation (:meth:`UninstallService.info`) : type d'installation,
  copies du modèle qu'Opportune peut supprimer, présence d'un Ollama personnel ;
- il **reçoit** la demande (:meth:`UninstallService.request`) et l'écrit dans un fichier du
  dossier de données ; la coquille surveille ce fichier, arrête l'API et Ollama, supprime les
  dossiers demandés puis lance le désinstalleur du système. L'API ne peut pas le faire
  elle-même : elle tient les bases SQLite ouvertes, et Ollama tient les fichiers du modèle.

Seule exception, faite ici et tout de suite : un modèle qu'Opportune a téléchargé **à travers
l'Ollama de la personne** se supprime en le demandant à cet Ollama, tant qu'il tourne.

Un modèle qui existait avant Opportune n'est jamais supprimé (cf. :mod:`app.model_origin`). Dans
l'Ollama de la personne, la copie d'Opportune se reconnaît à son **empreinte** (date de
modification) : si la personne a supprimé puis retéléchargé le modèle pour son propre usage,
l'empreinte ne correspond plus et la copie est conservée.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Mapping

from app.model_origin import ModelOriginStore, models_dir_from_env
from app.ollama_provision import OllamaUnreachable, delete_model, model_modified_at, model_with_tag

# Fichier de demande, écrit dans le dossier de données et lu par la coquille de bureau.
REQUEST_FILENAME = "uninstall-request.json"

# Sous-dossier du dossier de données où l'Ollama embarqué range ses modèles (cf. ``main.rs``).
APP_MODELS_DIRNAME = "ollama-models"

# Variables posées par la coquille de bureau. Absentes hors app de bureau (dev, tests) : la
# désinstallation n'est alors pas proposée.
INSTALL_KIND_ENV = "OPPORTUNE_INSTALL_KIND"
USER_OLLAMA_ENV = "OPPORTUNE_USER_OLLAMA"
APPIMAGE_ENV = "APPIMAGE"


class UninstallNotAvailable(Exception):
    """L'app ne tourne pas dans la coquille de bureau : personne ne traiterait la demande."""


class ModelRemovalFailed(Exception):
    """L'Ollama de la personne n'a pas supprimé le modèle (injoignable ou en erreur)."""


class UninstallService:
    """Décrit ce que la désinstallation peut supprimer, et enregistre la demande."""

    def __init__(
        self,
        *,
        data_dir: Path,
        origin: ModelOriginStore,
        model: str,
        host: str,
        environ: Mapping[str, str] | None = None,
        modified_at: Callable[..., str | None] = model_modified_at,
        delete: Callable[..., None] = delete_model,
    ) -> None:
        self._data_dir = data_dir
        self._origin = origin
        self._model = model_with_tag(model)
        self._host = host
        self._environ = os.environ if environ is None else environ
        self._modified_at = modified_at
        self._delete = delete

    def info(self) -> dict:
        """Situation de l'installation, pour l'écran de désinstallation."""
        install_kind = self._install_kind()
        app_copy_bytes = _directory_size(self._app_models_dir())
        # Un seul appel à Ollama : il sert à la fois à la présence du modèle et à son empreinte.
        current_fingerprint = self._current_fingerprint()
        return {
            "available": install_kind is not None,
            "install_kind": install_kind,
            "appimage_path": self._environ.get(APPIMAGE_ENV) if install_kind == "appimage" else None,
            "data_dir": str(self._data_dir),
            "model": {
                "name": self._model,
                "present": app_copy_bytes > 0 or current_fingerprint is not None,
                # Vrai s'il existe au moins une copie téléchargée par Opportune.
                "removable": app_copy_bytes > 0 or self._has_copy_in_user_ollama(current_fingerprint),
                # Taille de la copie rangée dans le dossier de l'app (0 s'il n'y en a pas). La
                # taille d'une copie rangée dans l'Ollama de la personne n'est pas connue.
                "app_copy_bytes": app_copy_bytes,
            },
            "user_has_own_ollama": self._environ.get(USER_OLLAMA_ENV, "").strip() == "1",
        }

    def request(self, *, remove_model: bool, remove_data: bool) -> None:
        """Enregistre la demande de désinstallation pour la coquille de bureau.

        Si ``remove_model`` et qu'Opportune a téléchargé le modèle à travers l'Ollama de la
        personne, cette copie est supprimée ici. L'ordre garantit qu'un échec ne laisse pas une
        désinstallation à moitié faite :

        1. la demande est d'abord écrite dans un fichier **temporaire** (un disque plein ou un
           dossier en lecture seule échoue ici, avant toute suppression) ;
        2. le modèle est supprimé d'Ollama ; un échec lève :class:`ModelRemovalFailed` et le
           fichier temporaire est retiré ;
        3. le fichier temporaire est renommé : c'est seulement là que la coquille voit la demande.
        """
        if self._install_kind() is None:
            raise UninstallNotAvailable("désinstallation disponible uniquement dans l'app de bureau")

        temporary = self._prepare_request({"remove_model": remove_model, "remove_data": remove_data})

        if remove_model and self._has_copy_in_user_ollama(self._current_fingerprint()):
            try:
                self._delete(self._model, host=self._host)
            except OllamaUnreachable as exc:
                temporary.unlink(missing_ok=True)
                raise ModelRemovalFailed(str(exc)) from exc
            self._origin.forget(self._model, self._user_ollama_models_dir())

        temporary.replace(self._data_dir / REQUEST_FILENAME)

    def _install_kind(self) -> str | None:
        return self._environ.get(INSTALL_KIND_ENV, "").strip() or None

    def _app_models_dir(self) -> Path:
        return self._data_dir / APP_MODELS_DIRNAME

    def _user_ollama_models_dir(self) -> str | None:
        """Dossier de modèles de l'Ollama en service **s'il n'est pas celui de l'app**.

        ``None`` couvre deux cas rangés sous la même clé dans le fichier d'origine : l'app
        réutilise l'Ollama de la personne (dossier inconnu), ou l'Ollama embarqué écrit dans le
        dossier de l'app (dont les copies sont comptées à part, par leur présence sur le disque).
        """
        models_dir = models_dir_from_env(self._environ)
        if models_dir is None or Path(models_dir) == self._app_models_dir():
            return None
        return models_dir

    def _serves_from_app_dir(self) -> bool:
        models_dir = models_dir_from_env(self._environ)
        return models_dir is not None and Path(models_dir) == self._app_models_dir()

    def _has_copy_in_user_ollama(self, current_fingerprint: str | None) -> bool:
        """Vrai si la copie présente dans l'Ollama (ou le dossier Ollama) de la personne est
        celle qu'Opportune a téléchargée.

        ``current_fingerprint`` est l'empreinte du modèle actuellement dans Ollama (``None`` s'il
        est absent ou qu'Ollama ne répond pas). Elle doit être égale à celle notée au
        téléchargement : sinon la personne a supprimé puis retéléchargé le modèle, et cette
        copie est la sienne. Sans empreinte notée, on ne supprime pas.
        """
        if self._serves_from_app_dir() or not current_fingerprint:
            return False
        recorded = self._origin.fingerprint_of(self._model, self._user_ollama_models_dir())
        return recorded is not None and recorded == current_fingerprint

    def _current_fingerprint(self) -> str | None:
        """Empreinte du modèle dans l'Ollama en service ; ``None`` s'il est absent ou
        qu'Ollama ne répond pas ; chaîne vide s'il est présent sans date connue."""
        try:
            return self._modified_at(self._model, host=self._host)
        except OllamaUnreachable:
            return None

    def _prepare_request(self, request: dict) -> Path:
        """Écrit la demande dans un fichier temporaire et rend son chemin. Le renommage final
        (fait par l'appelant) la rend visible d'un seul coup : la coquille ne lit jamais un
        fichier à moitié écrit."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        temporary = (self._data_dir / REQUEST_FILENAME).with_suffix(".tmp")
        temporary.write_text(json.dumps(request), encoding="utf-8")
        return temporary


def _directory_size(directory: Path) -> int:
    """Taille totale des fichiers d'un dossier, en octets (0 s'il est absent ou illisible)."""
    total = 0
    try:
        for root, _dirs, files in os.walk(directory):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total
