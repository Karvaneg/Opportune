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
from app.json_file_store import load_json_object
from app.paths import user_data_dir

# Nom du fichier de secrets dans le dossier de données de l'app.
_FILENAME = "adzuna_credentials.json"


def default_credentials_path(data_dir: Path | None = None) -> Path:
    """Chemin du fichier d'identifiants Adzuna dans un dossier de données.

    ``data_dir`` sélectionne l'emplacement : le dossier de l'app par défaut (espace réel), ou un
    sous-dossier propre à un autre espace (ex. la démo) — pour que les clés d'un espace ne
    fuitent pas dans l'autre.
    """
    return (data_dir or user_data_dir()) / _FILENAME


class AdzunaCredentialsStore:
    """Lit/écrit les identifiants Adzuna dans un fichier JSON local (secret, hors dépôt)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AdzunaCredentials | None:
        """Identifiants stockés, ou ``None`` si non configurés (fichier absent/illisible/vide).

        Tolérant par conception : toute anomalie de lecture (absent, JSON invalide, champs
        manquants/vides) est traitée comme « pas d'identifiants » plutôt que remontée en erreur.
        """
        data = load_json_object(self._path)
        if data is None:
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
        # Création **neuve** en permissions propriétaire (0o600) : un secret ne doit à aucun moment
        # être lisible par d'autres comptes. Le mode passé à ``os.open`` ne s'applique qu'à une
        # vraie création, pas à un fichier réouvert en place. On **supprime donc d'abord** tout
        # fichier préexistant (qui pourrait traîner des permissions plus larges), puis on crée avec
        # ``O_EXCL`` : le 0o600 est ainsi garanti par la création elle-même, sans dépendre d'un
        # ``chmod`` ultérieur (lequel échoue en silence sur certains montages, laissant le secret
        # lisible). Sans effet notable sous Windows (ACL), mais inoffensif — le dossier de données
        # y est déjà par-utilisateur (AppData).
        self._path.unlink(missing_ok=True)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)

    def is_configured(self) -> bool:
        """Vrai si des identifiants exploitables sont stockés."""
        return self.load() is not None

    def clear(self) -> None:
        """Supprime les identifiants stockés (le fichier). Sans effet s'il est déjà absent.

        Sert au « repartir de zéro » d'un espace : vider ses données doit aussi vider ses
        réglages, sans quoi l'espace repartirait avec des clés héritées.
        """
        self._path.unlink(missing_ok=True)


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
