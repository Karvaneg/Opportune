"""Suivi post-candidature : historique d'événements datés (OPP-223).

Le cycle de vie d'une candidature (``app.action.ApplicationAction``) s'arrête à « j'ai
candidaté » (``applied_at``). Ce module ajoute ce qui se passe **après** avoir postulé,
sous forme d'un **historique d'événements** (et non d'un statut unique qui s'écrase), sur
le même modèle que l'historique de validation d'une décision (``app.decision.DecisionEvent``) :
chaque événement porte un type, une date d'enregistrement et un commentaire éventuel.

Événements couverts :

- ``INTERVIEW`` : un entretien — **répétable** (plusieurs entretiens, chacun daté) ; sa date
  prévue est portée par ``event_date`` (souvent **future**, contrairement à ``at``) ;
- ``REJECTED`` : réponse **négative du recruteur** ;
- ``OFFER`` : offre reçue / candidature acceptée ;
- ``NO_RESPONSE`` : relance notée / sans réponse.

⚠️ Ne pas confondre ``REJECTED`` ici avec le ``rejected`` de ``app.decision`` : ce dernier
est *la décision de l'utilisateur de ne pas postuler*, pas la réponse du recruteur. Les deux
restent distincts, dans des domaines distincts.

Logique pure, sans persistance (cf. ``application_tracking_store``) ; l'horloge est injectable
pour des tests déterministes. L'historique est **append-only** : on ajoute un événement, on
n'en modifie ni n'en supprime. L'état courant d'une candidature se déduit de son dernier
événement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

# Types d'événement de suivi (le libellé lisible est du ressort du front).
INTERVIEW = "interview"
REJECTED = "rejected"
OFFER = "offer"
NO_RESPONSE = "no_response"
TRACKING_KINDS = (INTERVIEW, REJECTED, OFFER, NO_RESPONSE)

# Horloge par défaut : instant UTC au format ISO 8601.
Clock = Callable[[], str]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrackingError(Exception):
    """Type d'événement de suivi invalide (→ 400)."""


@dataclass(frozen=True)
class TrackingEvent:
    """Une entrée de l'historique de suivi d'une candidature.

    ``at`` horodate **l'enregistrement** de l'événement (toujours l'instant courant).
    ``event_date`` porte la **date métier** quand elle diffère de l'enregistrement — typiquement
    la date prévue d'un entretien, qui peut être dans le futur ; ``None`` quand l'événement se
    date lui-même (un rejet reçu aujourd'hui, par exemple).
    """

    kind: str
    at: str  # ISO 8601 — quand l'événement a été enregistré
    event_date: str | None = None  # ISO 8601 — date métier (entretien prévu…), ou None
    comment: str | None = None


def create_tracking_event(
    kind: str,
    *,
    event_date: str | None = None,
    comment: str | None = None,
    now: Clock = _utcnow,
) -> TrackingEvent:
    """Crée un événement de suivi horodaté à l'instant courant.

    ``kind`` doit appartenir à ``TRACKING_KINDS`` (``TrackingError`` sinon). ``comment`` est
    optionnel. ``event_date`` ne porte de sens que pour un ``INTERVIEW`` (la date prévue, souvent
    future) : la fournir pour un autre type est un ``TrackingError`` — sans quoi elle serait
    persistée mais jamais rendue (le front ne l'affiche que pour un entretien).
    """
    if kind not in TRACKING_KINDS:
        raise TrackingError(
            f"Type d'événement de suivi invalide : {kind!r} (attendu {TRACKING_KINDS})"
        )
    if event_date is not None and kind != INTERVIEW:
        raise TrackingError("event_date ne s'applique qu'à un entretien (interview)")
    return TrackingEvent(kind=kind, at=now(), event_date=event_date, comment=comment)
