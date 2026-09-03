"""Modèles de résultat d'Hermes (V2, OPP-060).

Hermes ne définit pas de nouveaux concepts métier : il assemble ceux qui existent.
``HermesRecommendation`` est le **résultat final** rendu par l'orchestrateur pour une
offre : la recommandation classée (OPP-0393) et la décision ``pending`` qui en a été
dérivée puis persistée (OPP-057). Les deux sont conservés pour que l'appelant dispose à
la fois du contexte de reco (score, atouts, écarts, justification) et de l'objet
décision validable.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.decision import Decision
from app.recommendation_service import OfferRecommendation


@dataclass(frozen=True)
class HermesRecommendation:
    """Une recommandation classée et la décision persistée qui en découle."""

    recommendation: OfferRecommendation
    decision: Decision


@dataclass(frozen=True)
class OfferEvaluation:
    """Trace d'une offre évaluée lors d'une exécution : son score et le statut de décision."""

    offer_id: str
    score: int
    decision_status: str  # statut de la décision persistée (``pending`` au départ)


@dataclass(frozen=True)
class HermesRun:
    """Trace complète et immuable d'une exécution Hermes pour un candidat (OPP-092).

    Journalise ce qu'une exécution a produit : quand (``executed_at``), pour qui
    (``candidate_id``), quelles offres évaluées avec quels scores et décisions
    (``evaluations``), et les erreurs éventuelles rencontrées par offre (``errors``).
    ``run_id`` identifie l'exécution de façon unique.
    """

    run_id: str
    candidate_id: str
    executed_at: str  # ISO 8601
    evaluations: tuple[OfferEvaluation, ...]
    errors: tuple[str, ...] = ()
