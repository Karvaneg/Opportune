"""Hermes — orchestrateur du pipeline métier (V2, OPP-060).

Hermes **coordonne** les services d'analyse déjà portés en V2 ; il ne réimplémente
aucune de leur logique. D'un ``candidate_id``, il déroule la boucle complète :

    profil + offres + recommandations   (RecommendationService)
        → décisions persistées           (decision_from_recommendation + DecisionStore)
        → résultat final                 (HermesRecommendation)

Le point d'entrée est ``HermesOrchestrator.recommend_for_candidate``.
"""

from __future__ import annotations

from hermes.discord_gateway import (
    build_decider,
    build_gateway_decider,
    process_interaction,
)
from hermes.models import HermesRecommendation, HermesRun, OfferEvaluation
from hermes.orchestrator import HermesOrchestrator
from hermes.push_runner import PushOutcome, PushRunner, build_push_runner
from hermes.review_resolution import ResolvedRun, resolve_run_review_items
from hermes.run_store import RunStore

__all__ = [
    "HermesOrchestrator",
    "HermesRecommendation",
    "HermesRun",
    "OfferEvaluation",
    "PushOutcome",
    "PushRunner",
    "ResolvedRun",
    "RunStore",
    "build_decider",
    "build_gateway_decider",
    "build_push_runner",
    "process_interaction",
    "resolve_run_review_items",
]
