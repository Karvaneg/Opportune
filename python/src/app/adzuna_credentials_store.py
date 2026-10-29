"""Stockage local des identifiants Adzuna saisis par l'utilisateur (OPP-222).

Les clés Adzuna (``app_id`` + ``app_key``) sont des **secrets** propres à chaque utilisateur :
elles ne sont ni codées en dur, ni committées, ni journalisées. Ce module les range dans un
fichier JSON du **dossier de données de l'app** (hors dépôt, local-first — cf. ``app.paths``),
en permissions restreintes au propriétaire (``0o600``).

Le store est volontairement tolérant en lecture : fichier absent, illisible ou JSON corrompu →
``load()`` rend ``None`` (pas d'identifiants), jamais une exception — la collecte rangera alors
l'absence dans ``source_error`` via ``resolve_adzuna_credentials``, au lieu de planter.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

from app.adzuna_client import AdzunaAuthError, AdzunaCredentials, credentials_from_env
from app.paths import user_data_dir

# Nom du fichier de secrets dans le dossier de données de l'app.
_FILENAME = "adzuna_credentials.json"


def default_credentials_path() -> Path:
    """Chemin du fichier d'identifiants Adzuna dans le dossier de données de l'app."""
    return user_data_dir() / _FILENAME


class AdzunaCredentialsStore:
    """Lit/écrit les identifiants Adzuna dans un fichier JSON local (secret, hors dépôt)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AdzunaCredentials | None:
        """Identifiants stockés, ou ``None`` si non configurés (fichier absent/illisible/vide).

        Tolérant par conception : toute anomalie de lecture (absent, JSON invalide, champs
        manquants/vides) est traitée comme « pas d'identifiants » plutôt que remontée en erreur.
        """
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        app_id = str(data.get("app_id") or "").strip()
        app_key = str(data.get("app_key") or "").strip()
        if not app_id or not app_key:
            return None
        return AdzunaCredentials(app_id=app_id, app_key=app_key)

    def save(self, app_id: str, app_key: str) -> None:
        """Persiste les identifiants (secret, permissions ``0o600``). Champs vides → ``ValueError``.

        Validation ici car un enregistrement de clés vides rendrait la collecte muette sans que
        l'utilisateur comprenne pourquoi. Le dossier parent est créé au besoin (1er lancement).
        """
        app_id = app_id.strip()
        app_key = app_key.strip()
        if not app_id or not app_key:
            raise ValueError("app_id et app_key sont requis (clés Adzuna)")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"app_id": app_id, "app_key": app_key})
        # Écriture puis restriction des permissions au propriétaire : un secret ne doit pas être
        # lisible par d'autres comptes de la machine. ``chmod`` est sans effet notable sous Windows
        # (ACL), mais inoffensif — le dossier de données y est déjà par-utilisateur (AppData).
        self._path.write_text(payload, encoding="utf-8")
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    def is_configured(self) -> bool:
        """Vrai si des identifiants exploitables sont stockés."""
        return self.load() is not None


def resolve_adzuna_credentials(
    store: AdzunaCredentialsStore, env: Mapping[str, str]
) -> AdzunaCredentials:
    """Identifiants Adzuna à utiliser : ceux **saisis par l'utilisateur** d'abord, sinon l'env.

    Le store (clés saisies dans l'UI) prime ; à défaut on retombe sur ``ADZUNA_APP_ID`` /
    ``ADZUNA_APP_KEY`` de l'environnement (câblage dev historique). Aucun des deux → la lève
    d'``AdzunaAuthError`` de ``credentials_from_env`` remonte (rangée en ``source_error`` par la
    collecte).
    """
    stored = store.load()
    if stored is not None:
        return stored
    return credentials_from_env(env)
