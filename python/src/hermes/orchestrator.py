"""Orchestrateur du pipeline métier (V2, OPP-060).

``HermesOrchestrator`` coordonne les services existants pour transformer un
``candidate_id`` en un jeu de **décisions persistées**, sans réimplémenter leur logique :

    RecommendationService.recommend   → profil + offres + match + score + action  [OPP-0393]
        → DecisionService.decide       → décision ``pending`` créée et persistée    [OPP-057]
        → DecisionService.validate     → validation humaine (approve/reject/defer)  [OPP-057]

Ses collaborateurs sont **injectés** (couplage aux services, pas aux implémentations
de persistance) : tout est testable avec de vrais dépôts SQLite en mémoire, sans réseau.
La gestion de l'horloge et de la persistance des décisions est déléguée à
``DecisionService`` — Hermes ne fait qu'enchaîner recommandation puis décision, et offre
un point d'entrée unique pour la validation humaine ultérieure.

Contrat de coordination :
- l'ordre des recommandations (score décroissant, tie-break déterministe) est **préservé**
  tel quel ; Hermes ne reclasse ni ne filtre — il délègue à ``RecommendationService`` ;
- une décision ``pending`` est créée puis persistée pour **chaque** recommandation
  retenue ; la validation humaine (approve/reject/defer) est appliquée à la demande via
  ``validate_decision`` ;
- ``UnknownCandidateError`` (candidat introuvable) et ``ValueError`` (``limit`` négatif,
  seuils incohérents) remontent depuis ``RecommendationService`` sans être masqués.
"""

from __future__ import annotations

from app.decision import Decision
from app.decision_service import DecisionService
from app.recommendation_service import OfferRecommendation, RecommendationService

from hermes.models import HermesRecommendation


class HermesOrchestrator:
    """Coordonne recommandation puis décision pour un candidat donné."""

    def __init__(
        self,
        recommendations: RecommendationService,
        decisions: DecisionService,
    ) -> None:
        self.recommendations = recommendations
        self.decisions = decisions

    def recommend_for_candidate(
        self,
        candidate_id: str,
        limit: int = 10,
    ) -> list[HermesRecommendation]:
        """Déroule la boucle complète pour ``candidate_id`` et rend le résultat final.

        Pour chacune des meilleures offres recommandées (au plus ``limit``), crée une
        décision ``pending`` dérivée de la recommandation et la persiste (via
        ``DecisionService``), puis retourne la liste des couples (recommandation,
        décision) dans l'ordre de classement.

        Propage ``UnknownCandidateError`` si le candidat est introuvable et ``ValueError``
        si ``limit`` est négatif — aucune décision n'est alors persistée.
        """
        recommendations = self.recommendations.recommend(candidate_id, limit=limit)

        results: list[HermesRecommendation] = []
        for recommendation in recommendations:
            decision = self.decisions.decide(recommendation, candidate_id)
            results.append(
                HermesRecommendation(recommendation=recommendation, decision=decision)
            )
        return results

    def validate_decision(
        self,
        candidate_id: str,
        offer_id: str,
        status: str,
        *,
        comment: str | None = None,
    ) -> Decision:
        """Applique une validation humaine à une décision déjà produite par Hermes.

        Ferme la boucle humaine (``approved`` / ``rejected`` / ``deferred``) sur une
        décision ``pending`` issue de ``recommend_for_candidate``. Délègue à
        ``DecisionService`` : propage ``UnknownDecisionError`` si la décision n'existe pas
        et ``DecisionError`` si le statut n'est pas un statut de validation humaine.
        """
        return self.decisions.validate(
            candidate_id, offer_id, status, comment=comment
        )

    def evaluate_for_candidate(
        self,
        candidate_id: str,
        limit: int = 10,
    ) -> dict:
        """Recommande puis **trie automatiquement** les offres par statut de décision.

        Pour chaque recommandation (au plus ``limit``), délègue le triage à
        ``DecisionService.evaluate`` (postuler → approved, à étudier → pending, ignorer →
        rejected) et regroupe les recommandations par statut. L'ordre de classement (score
        décroissant) est préservé au sein de chaque groupe.

        Retourne un dictionnaire structuré ::

            {
                "candidate_id": <str>,
                "recommendations": [<approuvées>],
                "pending_review": [<à relire>],
                "rejected": [<écartées>],
            }

        Propage ``UnknownCandidateError`` (candidat inconnu) et ``ValueError`` (``limit``
        négatif). Triage pur : aucune décision n'est persistée ici (la persistance passe
        par ``recommend_for_candidate`` / ``validate_decision``).

        RÈGLE : les statuts ``approved`` / ``pending`` / ``rejected`` de ce résultat sont
        des statuts de **pré-évaluation automatique**, pas des décisions humaines
        définitives. Nommer les deux registres distinctement lève l'ambiguïté ::

            auto_status = orchestrator.evaluate_for_candidate(candidate_id)   # pré-éval
            human_decision = orchestrator.validate_decision(cand, offer, ...)  # définitive
        """
        recommendations = self.recommendations.recommend(candidate_id, limit=limit)

        approved: list[OfferRecommendation] = []
        pending: list[OfferRecommendation] = []
        rejected: list[OfferRecommendation] = []
        buckets = {"approved": approved, "pending": pending, "rejected": rejected}

        for recommendation in recommendations:
            outcome = self.decisions.evaluate(recommendation)
            buckets[outcome.status].append(recommendation)

        return {
            "candidate_id": candidate_id,
            "recommendations": approved,
            "pending_review": pending,
            "rejected": rejected,
        }
