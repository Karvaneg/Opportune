"""Lecture tolérante d'un fichier JSON local (OPP-195).

Les stores de réglages locaux (identifiants Adzuna, flux RSS) partagent le **même contrat de
lecture** : un fichier absent, illisible ou au JSON corrompu ne doit jamais remonter d'exception,
mais être traité comme « pas de réglage » — la collecte range alors l'absence en ``source_error``
au lieu de planter. Ce module tient cette tolérance **une seule fois**, pour que les stores n'en
redéfinissent pas chacun leur copie (et ne divergent pas au premier correctif).
"""

from __future__ import annotations

import json
from pathlib import Path


def load_json_object(path: Path) -> dict | None:
    """Objet JSON (dict) lu depuis ``path``, ou ``None`` si absent/illisible/invalide/non-dict.

    Volontairement tolérant : ``OSError`` (absent, droits), JSON invalide
    (``ValueError``/``UnicodeDecodeError``) et racine non-dict sont tous traités comme « rien »,
    jamais remontés. La **forme** du contenu (champs attendus) reste à la charge de l'appelant.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None
