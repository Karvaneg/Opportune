"""Orchestrateur du pipeline métier (V2, OPP-060).

``HermesOrchestrator`` coordonne les services existants pour transformer un
``candidate_id`` en un jeu de **décisions persistées**, sans réimplémenter leur logique :

    RecommendationService.recommend   → profil + offres + match + score + action  [OPP-0393]
        → DecisionService.decide       → décision ``pending`` créée et persistée    [OPP-057]

Ses collaborateurs sont **injectés** (couplage aux services, pas aux implémentations
de persistance) : tout est testable avec de vrais dépôts SQLite en mémoire, sans réseau.
La gestion de l'horloge et de la persistance des décisions est déléguée à
``DecisionService`` — Hermes ne fait qu'enchaîner recommandation puis décision.

Contrat de coordination :
- l'ordre des recommandations (score décroissant, tie-break déterministe) est **préservé**
  tel quel ; Hermes ne reclasse ni ne filtre — il délègue à ``RecommendationService`` ;
- une décision ``pending`` est créée puis persistée pour **chaque** recommandation
  retenue ; la validation humaine (approve/reject/defer) reste hors de ce flux ;
- ``UnknownCandidateError`` (candidat introuvable) et ``ValueError`` (``limit`` négatif,
  seuils incohérents) remontent depuis ``RecommendationService`` sans être masqués.
"""

from __future__ import annotations

from app.decision_service import DecisionService
from app.recommendation_service import RecommendationService

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
