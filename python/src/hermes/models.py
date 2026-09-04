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

from app.decision import PENDING, Decision
from app.recommendation_service import OfferRecommendation


@dataclass(frozen=True)
class HermesRecommendation:
    """Une recommandation classée et la décision persistée qui en découle."""

    recommendation: OfferRecommendation
    decision: Decision


@dataclass(frozen=True)
class OfferEvaluation:
    """Snapshot riche d'une offre évaluée lors d'une exécution (OPP-095).

    Fige, **au moment du run**, ce qu'il faut pour restituer une recommandation paginée
    sans re-dérouler le pipeline — donc stable même si l'offre évolue ou disparaît :

    - ``score``, ``advisory_status`` et ``action`` : la pré-évaluation *automatique* figée
      (``advisory_status`` ∈ approved | pending | rejected ; ``action`` ∈ postuler |
      a_etudier | ignorer) ;
    - ``title`` / ``company`` / ``justification`` : le contexte de l'offre au run-time ;
    - ``decision_status`` : le statut de décision **au run-time** (``pending`` au départ).
      L'état de validation *humain* courant se relit en direct dans le ``DecisionStore`` —
      ce champ n'en est que la photo initiale (fallback).

    Les nouveaux champs ont un défaut : les runs sérialisés avant OPP-095 restent relisibles.
    """

    offer_id: str
    score: int
    decision_status: str = PENDING  # statut de décision au run-time (pending au départ)
    advisory_status: str = PENDING  # pré-éval auto figée : approved | pending | rejected
    action: str = ""  # action auto figée : postuler | a_etudier | ignorer
    title: str = ""
    company: str = ""
    justification: str = ""


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
