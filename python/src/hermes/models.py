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
