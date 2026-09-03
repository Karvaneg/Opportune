"""Hermes — orchestrateur du pipeline métier (V2, OPP-060).

Hermes **coordonne** les services d'analyse déjà portés en V2 ; il ne réimplémente
aucune de leur logique. D'un ``candidate_id``, il déroule la boucle complète :

    profil + offres + recommandations   (RecommendationService)
        → décisions persistées           (decision_from_recommendation + DecisionStore)
        → résultat final                 (HermesRecommendation)

Le point d'entrée est ``HermesOrchestrator.recommend_for_candidate``.
"""

from __future__ import annotations

from hermes.models import HermesRecommendation
from hermes.orchestrator import HermesOrchestrator

__all__ = ["HermesOrchestrator", "HermesRecommendation"]
