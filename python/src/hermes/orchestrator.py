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

import uuid
from datetime import datetime, timezone
from typing import Callable

from app.decision import Decision
from app.decision_service import DecisionService
from app.recommendation_service import OfferRecommendation, RecommendationService

from hermes.models import HermesRecommendation, HermesRun, OfferEvaluation
from hermes.run_store import RunRepository


def _utcnow_iso() -> str:
    """Instant UTC au format ISO 8601 (horloge par défaut des exécutions)."""
    return datetime.now(timezone.utc).isoformat()


class HermesOrchestrator:
    """Coordonne recommandation puis décision pour un candidat donné."""

    def __init__(
        self,
        recommendations: RecommendationService,
        decisions: DecisionService,
        *,
        runs: RunRepository | None = None,
        run_id: Callable[[], str] | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.recommendations = recommendations
        self.decisions = decisions
        # Traçabilité : dépôt d'exécutions (optionnel), fabrique d'identifiant d'exécution
        # et horloge — tous injectables pour des exécutions déterministes en test.
        self.runs = runs
        self._run_id = run_id or (lambda: uuid.uuid4().hex)
        self._now = now or _utcnow_iso

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

    def run_for_candidate(
        self,
        candidate_id: str,
        limit: int = 10,
    ) -> HermesRun:
        """Exécute la boucle pour ``candidate_id`` en **journalisant** l'exécution.

        Génère un ``run_id`` unique et un instant d'exécution, recommande les offres, puis
        pour chacune persiste la décision (via ``DecisionService.decide``) en traçant le
        score et le statut obtenus. Chaque erreur **par offre** est capturée dans le run et
        n'interrompt pas les suivantes : une exécution ultérieure reprend proprement, la
        persistance des décisions étant idempotente (upsert sur le couple candidat/offre,
        et toute validation humaine déjà posée est préservée).

        L'exécution est persistée si un dépôt de runs (``runs``) est configuré, puis
        retournée. Propage ``UnknownCandidateError`` (candidat inconnu) et ``ValueError``
        (``limit`` négatif) *avant* toute écriture : aucun run n'est alors enregistré.
        """
        run_id = self._run_id()
        executed_at = self._now()
        recommendations = self.recommendations.recommend(candidate_id, limit=limit)

        evaluations: list[OfferEvaluation] = []
        errors: list[str] = []
        for recommendation in recommendations:
            offer_id = recommendation.offer.id
            try:
                decision = self.decisions.decide(recommendation, candidate_id)
            except Exception as exc:  # noqa: BLE001 — toute erreur d'offre est tracée, jamais fatale
                # On conserve le type d'exception : une erreur de programmation
                # (AttributeError, TypeError…) reste diagnosticable dans la trace du run
                # au lieu d'être noyée dans un message anonyme.
                errors.append(f"{offer_id}: {type(exc).__name__}: {exc}")
                continue
            evaluations.append(
                OfferEvaluation(
                    offer_id=offer_id,
                    score=recommendation.score,
                    decision_status=decision.status,
                )
            )

        run = HermesRun(
            run_id=run_id,
            candidate_id=candidate_id,
            executed_at=executed_at,
            evaluations=tuple(evaluations),
            errors=tuple(errors),
        )
        if self.runs is not None:
            self.runs.save(run)
        return run
