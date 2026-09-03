"""Orchestrateur du pipeline métier (V2, OPP-060).

``HermesOrchestrator`` coordonne les services existants pour transformer un
``candidate_id`` en un jeu de **décisions persistées**, sans réimplémenter leur logique :

    RecommendationService.recommend   → profil + offres + match + score + action  [OPP-0393]
        → decision_from_recommendation → décision ``pending`` (immuable, historisée)  [OPP-057]
        → DecisionRepository.save      → persistance (upsert sur le couple candidat/offre)

Ses collaborateurs sont **injectés** (couplage aux protocoles, pas aux implémentations) :
tout est testable avec de vrais dépôts SQLite en mémoire, sans réseau. L'horloge est
injectable pour des dates de décision déterministes en test.

Contrat de coordination :
- l'ordre des recommandations (score décroissant, tie-break déterministe) est **préservé**
  tel quel ; Hermes ne reclasse ni ne filtre — il délègue à ``RecommendationService`` ;
- une décision ``pending`` est créée puis persistée pour **chaque** recommandation
  retenue ; la validation humaine (approve/reject/defer) reste hors de ce flux ;
- ``UnknownCandidateError`` (candidat introuvable) et ``ValueError`` (``limit`` négatif,
  seuils incohérents) remontent depuis ``RecommendationService`` sans être masqués.
"""

from __future__ import annotations

from app.decision import Clock, decision_from_recommendation
from app.decision_store import DecisionRepository
from app.recommendation_service import RecommendationService

from hermes.models import HermesRecommendation


class HermesOrchestrator:
    """Coordonne recommandation puis décision pour un candidat donné."""

    def __init__(
        self,
        recommendations: RecommendationService,
        decisions: DecisionRepository,
        *,
        now: Clock | None = None,
    ) -> None:
        self.recommendations = recommendations
        self.decisions = decisions
        # Horloge optionnelle : ``None`` laisse ``decision_from_recommendation`` utiliser
        # son horloge UTC par défaut ; une horloge injectée rend les tests déterministes.
        self._now = now

    def recommend_for_candidate(
        self,
        candidate_id: str,
        limit: int = 10,
    ) -> list[HermesRecommendation]:
        """Déroule la boucle complète pour ``candidate_id`` et rend le résultat final.

        Pour chacune des meilleures offres recommandées (au plus ``limit``), crée une
        décision ``pending`` dérivée de la recommandation et la persiste, puis retourne
        la liste des couples (recommandation, décision) dans l'ordre de classement.

        Propage ``UnknownCandidateError`` si le candidat est introuvable et ``ValueError``
        si ``limit`` est négatif — aucune décision n'est alors persistée.
        """
        recommendations = self.recommendations.recommend(candidate_id, limit=limit)

        results: list[HermesRecommendation] = []
        for recommendation in recommendations:
            if self._now is None:
                decision = decision_from_recommendation(recommendation, candidate_id)
            else:
                decision = decision_from_recommendation(
                    recommendation, candidate_id, now=self._now
                )
            self.decisions.save(decision)
            results.append(
                HermesRecommendation(recommendation=recommendation, decision=decision)
            )
        return results
