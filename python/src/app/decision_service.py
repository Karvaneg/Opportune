"""Service de décision (V2, OPP-060).

Coordonne le **cycle de vie** d'une décision métier — création à partir d'une
recommandation (OPP-0393) puis validation humaine (OPP-057) — et sa **persistance**
(``DecisionRepository``). Il ne réimplémente pas la logique de décision (fonctions pures
de ``app.decision``) : il l'orchestre avec le dépôt, offrant un unique point d'entrée
injectable au métier (ex. l'orchestrateur Hermes).

L'horloge est injectable pour des dates déterministes en test ; ``None`` laisse les
fonctions de ``app.decision`` utiliser leur horloge UTC par défaut.
"""

from __future__ import annotations

from app.decision import (
    PENDING,
    Clock,
    Decision,
    decision_from_recommendation,
    decision_id,
    validate,
)
from app.decision_store import DecisionRepository
from app.recommendation_service import OfferRecommendation


class UnknownDecisionError(Exception):
    """Aucune décision persistée ne correspond au couple (candidat, offre) fourni."""


class DecisionService:
    """Crée, valide et persiste des décisions métier."""

    def __init__(self, decisions: DecisionRepository, *, now: Clock | None = None) -> None:
        self.decisions = decisions
        self._now = now

    def _clock_kwargs(self) -> dict[str, Clock]:
        """Passe l'horloge injectée si présente, sinon laisse ``app.decision`` par défaut."""
        return {} if self._now is None else {"now": self._now}

    def decide(self, recommendation: OfferRecommendation, candidate_id: str) -> Decision:
        """Crée (ou rafraîchit) une décision ``pending`` dérivée d'une recommandation.

        La persistance est un upsert sur le couple (candidat, offre) : re-décider la même
        offre pour le même candidat met à jour la ligne au lieu de la dupliquer. Une
        décision **déjà validée** par un humain (``approved`` / ``rejected`` / ``deferred``)
        est en revanche **préservée telle quelle** : re-dérouler la recommandation ne doit
        jamais écraser une validation humaine ni son historique.
        """
        stored_id = decision_id(candidate_id, recommendation.offer.id)
        existing = self.decisions.get(stored_id)
        if existing is not None and existing.status != PENDING:
            return existing
        decision = decision_from_recommendation(
            recommendation, candidate_id, **self._clock_kwargs()
        )
        self.decisions.save(decision)
        return decision

    def validate(
        self,
        candidate_id: str,
        offer_id: str,
        status: str,
        *,
        comment: str | None = None,
    ) -> Decision:
        """Applique une validation humaine à une décision existante et la persiste.

        Lève ``UnknownDecisionError`` si la décision est introuvable, et ``DecisionError``
        (depuis ``app.decision``) si le statut de validation n'est pas humain. L'action,
        le score et la justification d'origine restent immuables ; le changement est
        historisé.
        """
        stored_id = decision_id(candidate_id, offer_id)
        existing = self.decisions.get(stored_id)
        if existing is None:
            raise UnknownDecisionError(f"Décision introuvable : {stored_id!r}")
        updated = validate(existing, status, comment=comment, **self._clock_kwargs())
        self.decisions.save(updated)
        return updated
