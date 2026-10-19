"""Flux d'activité récente d'un candidat, pour le cockpit (V2, OPP-165).

Agrège en un **journal transversal** des événements jusque-là éparpillés (décision tranchée,
lettre de motivation, candidature déclarée, offre ajoutée au catalogue) — il n'existait
auparavant qu'un historique *par recommandation*. Chaque événement est horodaté, porte un
libellé FR prêt à afficher et une **cible cliquable** (fiche de recommandation ou offre).

Ce module est **pur** : il définit le modèle, construit les événements typés et les classe du
plus récent au plus ancien. La collecte dans les différents dépôts est faite par l'appelant
(l'orchestrateur), qui lui passe les ingrédients.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

# Horodatage « plancher » pour les événements sans date connue (offre backfillée) ou non
# parsables : avec un tri décroissant, ils se classent en dernier.
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

# Cibles cliquables possibles d'un événement.
TARGET_RECOMMENDATION = "recommendation"  # → fiche /recommendations/{id}
TARGET_OFFER = "offer"  # → catalogue /offres

# Libellés FR d'une décision humaine tranchée.
_DECISION_LABELS = {
    "approved": "Candidature approuvée",
    "rejected": "Offre rejetée",
    "deferred": "Décision reportée",
}


@dataclass(frozen=True)
class ActivityEvent:
    """Un événement du flux d'activité, prêt à afficher et à lier."""

    type: str  # letter | decision | application | offer
    at: str  # horodatage ISO 8601
    label: str  # libellé FR complet
    target_kind: str  # recommendation | offer
    target_id: str


def decision_event(status: str, at: str, offer_title: str, recommendation_id: str) -> ActivityEvent:
    """Événement « décision tranchée » (approuvée / rejetée / reportée)."""
    label = _DECISION_LABELS.get(status, "Décision mise à jour")
    return ActivityEvent("decision", at, f"{label} — {offer_title}", TARGET_RECOMMENDATION, recommendation_id)


def letter_event(at: str, offer_title: str, recommendation_id: str) -> ActivityEvent:
    """Événement « lettre de motivation » (générée ou éditée)."""
    return ActivityEvent(
        "letter", at, f"Lettre de motivation — {offer_title}", TARGET_RECOMMENDATION, recommendation_id
    )


def application_event(at: str, offer_title: str, recommendation_id: str) -> ActivityEvent:
    """Événement « candidature déclarée »."""
    return ActivityEvent(
        "application", at, f"Candidature déclarée — {offer_title}", TARGET_RECOMMENDATION, recommendation_id
    )


def offer_event(at: str, offer_title: str, offer_id: str) -> ActivityEvent:
    """Événement « offre ajoutée au catalogue » (pool partagé, non lié à un candidat)."""
    return ActivityEvent("offer", at, f"Offre ajoutée — {offer_title}", TARGET_OFFER, offer_id)


def _instant(iso: str) -> datetime:
    """Instant UTC d'un horodatage ISO, pour un tri chronologique fiable.

    Normalise en UTC (``+00:00``, offset explicite ou heure naïve supposée UTC) afin de comparer
    sans dépendre de la *forme* textuelle : une comparaison lexicographique mésordonnerait un
    ``+02:00`` vis-à-vis d'un ``+00:00``. Horodatage vide ou non parsable → ``_EPOCH`` (dernier).
    """
    try:
        dt = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return _EPOCH
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def most_recent(events: Iterable[ActivityEvent], *, limit: int) -> list[ActivityEvent]:
    """Classe les événements du plus récent au plus ancien et garde les ``limit`` premiers.

    Tri sur l'instant UTC (``_instant``) : robuste aux fuseaux/formats hétérogènes. Un horodatage
    vide (offre backfillée sans date connue) se classe en dernier. ``limit`` négatif → vide.
    """
    if limit <= 0:
        return []
    ordered = sorted(events, key=lambda e: _instant(e.at), reverse=True)
    return ordered[:limit]
