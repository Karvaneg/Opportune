"""Stockage local des URLs de flux RSS saisies par l'utilisateur (OPP-195).

Faute de flux RSS d'offres **françaises** gratuit et fiable, la collecte RSS n'embarque aucun
flux par défaut : c'est l'utilisateur qui colle les URLs des flux qu'il veut suivre (même
principe que les clés Adzuna, mais ici ce ne sont **pas des secrets** — on les relit donc
telles quelles dans l'UI). Ce module les range dans un fichier JSON du **dossier de données de
l'app** (hors dépôt, local-first — cf. ``app.paths``).

Comme le store Adzuna, la lecture est volontairement tolérante : fichier absent, illisible ou
JSON corrompu → ``load()`` rend une liste vide (aucun flux), jamais une exception — la collecte
rangera alors l'absence dans ``source_error``, au lieu de planter.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.paths import user_data_dir

# Nom du fichier de flux dans le dossier de données de l'app.
_FILENAME = "rss_feeds.json"


def default_rss_feeds_path(data_dir: Path | None = None) -> Path:
    """Chemin du fichier de flux RSS dans un dossier de données.

    ``data_dir`` sélectionne l'emplacement : le dossier de l'app par défaut (espace réel), ou un
    sous-dossier propre à un autre espace (ex. la démo) — pour que les réglages d'un espace ne
    fuitent pas dans l'autre.
    """
    return (data_dir or user_data_dir()) / _FILENAME


def _clean(urls: object) -> list[str]:
    """Normalise une liste d'URLs : chaînes ``http(s)`` non vides, espaces retirés, ordre gardé.

    Tolère tout en entrée (relecture d'un JSON quelconque) : un élément non-chaîne ou une URL
    sans schéma ``http``/``https`` est ignoré plutôt que remonté en erreur.
    """
    if not isinstance(urls, list):
        return []
    cleaned: list[str] = []
    for item in urls:
        if not isinstance(item, str):
            continue
        url = item.strip()
        if url.startswith(("http://", "https://")):
            cleaned.append(url)
    return cleaned


class RssFeedsStore:
    """Lit/écrit la liste des URLs de flux RSS dans un fichier JSON local (hors dépôt)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[str]:
        """URLs de flux stockées, ou liste vide si non configurées (absent/illisible/invalide).

        Tolérant par conception : toute anomalie de lecture est traitée comme « aucun flux ».
        """
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return []
        if not isinstance(data, dict):
            return []
        return _clean(data.get("feeds"))

    def save(self, feeds: list[str]) -> list[str]:
        """Persiste les URLs (après nettoyage) et rend la liste réellement enregistrée.

        Validation ici : une liste sans aucune URL ``http(s)`` exploitable → ``ValueError``
        (enregistrer « rien » rendrait la collecte muette sans que l'utilisateur comprenne).
        Le dossier parent est créé au besoin (1er lancement).
        """
        cleaned = _clean(feeds)
        if not cleaned:
            raise ValueError("au moins une URL de flux http(s) est requise")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"feeds": cleaned}), encoding="utf-8")
        return cleaned

    def is_configured(self) -> bool:
        """Vrai si au moins une URL de flux exploitable est stockée."""
        return bool(self.load())

    def clear(self) -> None:
        """Supprime les flux stockés (le fichier). Sans effet s'il est déjà absent.

        Sert au « repartir de zéro » d'un espace : vider ses données doit aussi vider ses
        réglages, sans quoi l'espace repartirait avec des flux hérités.
        """
        self._path.unlink(missing_ok=True)
