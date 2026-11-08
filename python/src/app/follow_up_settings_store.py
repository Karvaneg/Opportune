"""Stockage local des délais de relance réglés par l'utilisateur (OPP-235).

Même principe que les flux RSS (``rss_feeds_store``) : un fichier JSON dans le dossier de
réglages de l'espace. Lecture tolérante : fichier absent, illisible ou liste invalide → délais par
défaut (cf. ``app.follow_up``), jamais une exception.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.follow_up import DEFAULT_AFTER_APPLICATION, DEFAULT_AFTER_INTERVIEW, FollowUpSchedule
from app.json_file_store import load_json_object
from app.paths import user_data_dir

_FILENAME = "follow_up.json"

# Bornes d'une saisie : au plus 10 relances par cas, chacune à 1 an maximum.
MAX_DELAYS = 10
MAX_DAYS = 365


def default_follow_up_path(data_dir: Path | None = None) -> Path:
    """Chemin du fichier des délais de relance dans un dossier de réglages (cf. RSS)."""
    return (data_dir or user_data_dir()) / _FILENAME


def validate_delays(delays: object, label: str) -> tuple[int, ...]:
    """Délais valides (entiers de 1 à 365, strictement croissants, 10 au plus) ; ``ValueError`` sinon.

    Une liste vide est permise : aucune relance pour ce cas.
    """
    if not isinstance(delays, list) or len(delays) > MAX_DELAYS:
        raise ValueError(f"{label} : une liste de {MAX_DELAYS} nombres de jours au plus")
    if any(isinstance(d, bool) or not isinstance(d, int) for d in delays):
        raise ValueError(f"{label} : chaque délai doit être un nombre entier de jours")
    if any(not 1 <= d <= MAX_DAYS for d in delays):
        raise ValueError(f"{label} : chaque délai doit être compris entre 1 et {MAX_DAYS} jours")
    if any(a >= b for a, b in zip(delays, delays[1:])):
        raise ValueError(f"{label} : les délais doivent être croissants, sans doublon")
    return tuple(delays)


def _valid_or(delays: object, default: tuple[int, ...]) -> tuple[int, ...]:
    """``delays`` s'ils sont valides, sinon ``default``."""
    try:
        return validate_delays(delays, "délais")
    except ValueError:
        return default


class FollowUpSettingsStore:
    """Lit/écrit les délais de relance dans un fichier JSON local."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> FollowUpSchedule:
        """Délais enregistrés, ou délais par défaut si absents ou invalides.

        Chaque liste est lue à part : une liste invalide revient à sa valeur par défaut sans
        faire perdre l'autre.
        """
        data = load_json_object(self._path)
        if data is None:
            return FollowUpSchedule()
        return FollowUpSchedule(
            after_application=_valid_or(data.get("after_application"), DEFAULT_AFTER_APPLICATION),
            after_interview=_valid_or(data.get("after_interview"), DEFAULT_AFTER_INTERVIEW),
        )

    def save(self, after_application: object, after_interview: object) -> FollowUpSchedule:
        """Valide et enregistre les délais ; rend ce qui a été enregistré. ``ValueError`` si invalide."""
        schedule = FollowUpSchedule(
            after_application=validate_delays(
                after_application, "Relances après une candidature"
            ),
            after_interview=validate_delays(after_interview, "Relances après un entretien"),
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Écriture atomique : fichier temporaire puis remplacement. Une écriture interrompue
        # laisse l'ancien fichier intact au lieu d'un JSON tronqué relu comme « délais par défaut ».
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "after_application": list(schedule.after_application),
                    "after_interview": list(schedule.after_interview),
                }
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)
        return schedule

    def clear(self) -> None:
        """Supprime le fichier (retour aux délais par défaut). Sans effet s'il est absent."""
        self._path.unlink(missing_ok=True)
