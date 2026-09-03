"""Décision et validation des recommandations (V2, OPP-057).

Transforme une recommandation (OPP-0393) en **décision métier** validable par un humain.
La décision capte l'action automatique (postuler / à étudier / ignorer) issue du score,
puis suit un statut de validation : ``pending`` à la création, que l'humain fait passer
à ``approved`` / ``rejected`` / ``deferred``.

Invariants :
- l'action automatique, le score et la justification d'origine sont **immuables** — la
  recommandation initiale n'est jamais perdue ;
- chaque changement de statut est **historisé** (statut + date + commentaire) ;
- une (re)validation vers ``approved`` / ``rejected`` / ``deferred`` est toujours
  permise (« confirmer ou modifier »), mais on ne revient jamais à ``pending``.

Logique pure, sans persistance (cf. ``decision_store``) ; l'horloge est injectable pour
des tests déterministes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from app.recommendation_service import OfferRecommendation

# Statut initial (automatique) et statuts posés par la validation humaine.
PENDING = "pending"
HUMAN_STATUSES = ("approved", "rejected", "deferred")
VALIDATION_STATUSES = (PENDING, *HUMAN_STATUSES)

# Horloge par défaut : instant UTC au format ISO 8601.
Clock = Callable[[], str]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionError(Exception):
    """Transition de validation invalide."""


@dataclass(frozen=True)
class DecisionEvent:
    """Une entrée d'historique : statut posé, date, commentaire éventuel."""

    status: str
    at: str  # ISO 8601
    comment: str | None = None


@dataclass(frozen=True)
class Decision:
    """Décision métier sur une opportunité, validable par un humain."""

    id: str
    candidate_id: str
    offer_id: str
    action: str  # auto (immuable) : postuler | a_etudier | ignorer
    score: int  # immuable
    justification: str  # immuable — recommandation d'origine préservée
    status: str = PENDING
    comment: str | None = None
    history: tuple[DecisionEvent, ...] = ()


def _escape(part: str) -> str:
    """Échappe le séparateur pour rendre la concaténation d'id sans collision."""
    return part.replace("\\", "\\\\").replace(":", "\\:")


def decision_id(candidate_id: str, offer_id: str) -> str:
    """Identifiant stable d'une décision : un couple (candidat, offre) est unique.

    Les composants sont échappés : un ``:`` dans un id ne peut pas créer de collision
    entre deux couples distincts (ex. ``("a:b", "c")`` vs ``("a", "b:c")``).
    """
    return f"{_escape(candidate_id)}:{_escape(offer_id)}"


def create_decision(
    *,
    candidate_id: str,
    offer_id: str,
    action: str,
    score: int,
    justification: str,
    now: Clock = _utcnow,
) -> Decision:
    """Crée une décision au statut ``pending``, avec un premier événement d'historique."""
    at = now()
    return Decision(
        id=decision_id(candidate_id, offer_id),
        candidate_id=candidate_id,
        offer_id=offer_id,
        action=action,
        score=score,
        justification=justification,
        status=PENDING,
        comment=None,
        history=(DecisionEvent(status=PENDING, at=at, comment=None),),
    )


def decision_from_recommendation(
    recommendation: "OfferRecommendation", candidate_id: str, *, now: Clock = _utcnow
) -> Decision:
    """Crée une décision ``pending`` à partir d'une recommandation (OPP-0393)."""
    return create_decision(
        candidate_id=candidate_id,
        offer_id=recommendation.offer.id,
        action=recommendation.action,
        score=recommendation.score,
        justification=recommendation.justification,
        now=now,
    )


def validate(
    decision: Decision, status: str, *, comment: str | None = None, now: Clock = _utcnow
) -> Decision:
    """Applique une validation humaine ; retourne une nouvelle décision (immuable).

    ``status`` doit appartenir à ``HUMAN_STATUSES`` (``DecisionError`` sinon). L'action
    auto, le score et la justification sont conservés ; le changement est historisé.
    """
    if status not in HUMAN_STATUSES:
        raise DecisionError(
            f"Statut de validation invalide : {status!r} (attendu {HUMAN_STATUSES})"
        )
    event = DecisionEvent(status=status, at=now(), comment=comment)
    return replace(
        decision, status=status, comment=comment, history=(*decision.history, event)
    )
