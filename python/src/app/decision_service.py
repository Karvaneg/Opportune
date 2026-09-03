"""Service de décision (V2, OPP-060).

Coordonne le **cycle de vie** d'une décision métier — création à partir d'une
recommandation (OPP-0393) puis validation humaine (OPP-057) — et sa **persistance**
(``DecisionRepository``). Il ne réimplémente pas la logique de décision (fonctions pures
de ``app.decision``) : il l'orchestre avec le dépôt, offrant un unique point d'entrée
injectable au métier (ex. l'orchestrateur Hermes).

L'horloge est injectable pour des dates déterministes en test ; ``None`` laisse les
fonctions de ``app.decision`` utiliser leur horloge UTC par défaut.

Deux registres distincts à ne pas confondre :
- ``evaluate`` → **pré-évaluation automatique** (pure, sans persistance) : un tri
  déterministe de la recommandation en ``approved`` / ``pending`` / ``rejected``.
- ``decide`` / ``validate`` → **décision métier** persistée, dont ``validate`` porte la
  validation humaine définitive (historisée).
"""

from __future__ import annotations

from dataclasses import dataclass

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

# --- Pré-évaluation automatique (≠ décision humaine) --------------------------
#
# RÈGLE : les statuts ``approved`` / ``pending`` / ``rejected`` produits ici sont des
# statuts de **pré-évaluation** — un tri automatique et déterministe fondé sur l'action
# recommandée (issue du score). Ce ne sont **pas** des décisions humaines définitives :
# ils n'engagent rien, ne sont pas persistés et peuvent être recalculés à volonté. La
# décision métier définitive passe, elle, par la validation humaine (``validate``), seule
# à être historisée et persistée.
#
#   postuler  → approved   (candidature pressentie)
#   a_etudier → pending    (à faire relire par un humain)
#   ignorer   → rejected   (écartée)
# Toute autre action (ex. ``indeterminee``, données insuffisantes) → pending par
# prudence : on ne pré-approuve ni ne pré-rejette ce qu'on ne sait pas trancher.
APPROVED = "approved"
REJECTED = "rejected"
PRE_EVALUATION_STATUSES = (APPROVED, PENDING, REJECTED)
_ACTION_TO_STATUS = {
    "postuler": APPROVED,
    "a_etudier": PENDING,
    "ignorer": REJECTED,
}


@dataclass(frozen=True)
class PreEvaluation:
    """Pré-évaluation automatique d'une recommandation (≠ décision humaine définitive).

    ``status`` est un statut de pré-évaluation (``approved`` / ``pending`` / ``rejected``),
    pas une décision validée par un humain : rien n'est persisté ni engagé.
    """

    recommendation: OfferRecommendation
    status: str


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

    def evaluate(self, recommendation: OfferRecommendation) -> PreEvaluation:
        """Pré-évalue une recommandation en un statut de **pré-évaluation automatique**.

        Politique déterministe fondée sur l'action recommandée (``postuler`` → approved,
        ``a_etudier`` → pending, ``ignorer`` → rejected ; toute autre → pending). Pure et
        sans persistance. Le statut retourné n'est **pas** une décision humaine définitive
        (cf. la RÈGLE ci-dessus et ``validate``, qui, elle, historise et persiste).
        """
        status = _ACTION_TO_STATUS.get(recommendation.action, PENDING)
        return PreEvaluation(recommendation=recommendation, status=status)
