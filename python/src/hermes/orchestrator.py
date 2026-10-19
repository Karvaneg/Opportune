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
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from app.candidate_activity import (
    ActivityEvent,
    application_event,
    decision_event,
    letter_event,
    most_recent,
    offer_event,
)
from app.candidate_stats import (
    A_ETUDIER,
    A_POSTULER,
    POSTULE,
    CandidateStats,
    build_candidate_stats,
    funnel_stage,
)
from app.decision import HUMAN_STATUSES, Decision
from app.decision_service import DecisionService
from app.offer import Offer
from app.recommendation_service import (
    OfferCatalogEntry,
    OfferRecommendation,
    RecommendationService,
    UnknownCandidateError,
)

from hermes.models import (
    HermesRecommendation,
    HermesRun,
    HermesRunSummary,
    OfferEvaluation,
)
from hermes.run_store import RunRepository

# Étapes d'entonnoir filtrables du catalogue (OPP-164) ; un ``stage`` hors de cet ensemble
# est ignoré (catalogue complet), aligné sur ``isFunnelStage`` côté front.
_FUNNEL_STAGES = frozenset({A_ETUDIER, A_POSTULER, POSTULE})


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
        return self._bucket(candidate_id, recommendations)

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
        recommendations = self.recommendations.recommend(candidate_id, limit=limit)
        run, _ = self._execute(candidate_id, recommendations)
        return run

    def run_and_evaluate_for_candidate(
        self,
        candidate_id: str,
        limit: int = 10,
        *,
        filters: dict | None = None,
        only_new: bool = False,
    ) -> HermesRun:
        """Recommande **une seule fois**, journalise l'exécution *et* pré-évalue, d'un bloc.

        Combine ``run_for_candidate`` (persistance + trace) et la pré-évaluation en une
        **unique** passe de recommandation — au lieu de dérouler deux fois le pipeline.
        Surtout, garantit la cohérence entre ce qui est persisté et ce qui est présenté :
        une offre dont la décision échoue est tracée dans ``run.errors`` et **exclue** des
        évaluations du run (jamais présentée comme évaluée).

        ``filters`` (optionnel) restreint le stock **avant** classement et coupe ``limit``
        (cf. ``RecommendationService.recommend``) : seules les offres retenues sont donc
        évaluées, persistées et tracées dans le run.

        ``only_new`` (OPP-150) : si vrai, le run n'évalue que les offres **nouvelles** —
        celles sans décision déjà posée pour le candidat sont exclues en amont. Évite de
        re-lister à chaque run les offres déjà traitées (symptôme OPP-150) ; une offre
        ancienne se repasse à la main (re-score ciblé, cf. ``rescore_offer``). Un run sans
        nouveauté est alors légitimement vide — et, s'il n'a produit *aucune* erreur, n'est
        **pas persisté** (cf. ``_execute``) pour ne pas polluer la liste des runs. **Réservé
        au run piloté depuis le front** :
        le push Discord garde ``only_new=False`` (il dédoublonne via ses propres soumissions,
        et doit pouvoir re-pousser une offre après un ``forget``).

        Retourne le ``run`` : chaque ``OfferEvaluation`` y fige déjà son ``advisory_status``
        (pré-éval automatique), rendant un tri en buckets superflu ici. Propage
        ``UnknownCandidateError`` et ``ValueError`` avant toute écriture.
        """
        exclude = (
            {d.offer_id for d in self.decisions.list_for_candidate(candidate_id)}
            if only_new
            else None
        )
        recommendations = self.recommendations.recommend(
            candidate_id, limit=limit, filters=filters, exclude_offer_ids=exclude
        )
        run, _ = self._execute(candidate_id, recommendations)
        return run

    def rescore_offer(self, candidate_id: str, offer_id: str) -> Decision | None:
        """Re-score **une** offre à la demande et met à jour sa décision (OPP-150).

        Sert à repasser une offre « ancienne » (déjà traitée par un run passé, donc jamais
        ré-évaluée automatiquement). Retourne ``None`` si l'offre est introuvable ou non
        évaluable. Une décision **déjà validée** par un humain est préservée telle quelle
        (``DecisionService.decide`` ne réécrit qu'une décision ``pending``) : le re-score
        ne peut jamais écraser un arbitrage. Propage ``UnknownCandidateError``.
        """
        recommendation = self.recommendations.recommend_one(candidate_id, offer_id)
        if recommendation is None:
            return None
        return self.decisions.decide(recommendation, candidate_id)

    def candidate_stats(
        self, candidate_id: str, *, applied_recommendation_ids: Collection[str] = ()
    ) -> CandidateStats:
        """Entonnoir d'avancement du candidat pour le cockpit (OPP-163 / révisé OPP-164).

        Classe **chaque** offre du pool selon la **décision humaine** et l'état de candidature
        (à étudier / à postuler / postulé), et non selon le score de l'algo — voir
        ``candidate_stats.funnel_stage``. ``applied_recommendation_ids`` (les offres candidatées,
        connues de la couche qui câble ``ActionService``) distingue « postulé » d'« à postuler ».

        Déterministe, sans scoring : une simple lecture des décisions + du pool. Propage
        ``UnknownCandidateError`` si le candidat est introuvable.
        """
        if self.recommendations.profiles.get(candidate_id) is None:
            raise UnknownCandidateError(f"Candidat introuvable : {candidate_id!r}")
        state = self.funnel_state_by_offer(candidate_id, applied_recommendation_ids)
        stages = (funnel_stage(status, applied) for status, applied in state.values())
        return build_candidate_stats(stages)

    def funnel_state_by_offer(
        self, candidate_id: str, applied_recommendation_ids: Collection[str] = ()
    ) -> dict[str, tuple[str | None, bool]]:
        """``(statut de décision, candidaté ?)`` par offre du pool — **source unique** de l'entonnoir.

        Alimente à la fois les compteurs (``candidate_stats``) et l'annotation/le filtre par
        étape du catalogue (OPP-164), pour que cartes du cockpit et liste concordent toujours.
        Lecture seule (décisions + pool), sans scoring. L'ordre des clés suit celui du pool
        (plus récentes d'abord), exploité pour paginer un catalogue filtré par étape.

        Ne vérifie pas l'existence du candidat (les décisions d'un candidat inconnu sont
        simplement vides) : le scoring en aval lève ``UnknownCandidateError`` le cas échéant.
        """
        applied = set(applied_recommendation_ids)
        decisions = self.decisions.list_for_candidate(candidate_id)
        status_by_offer = {d.offer_id: d.status for d in decisions}
        applied_offer_ids = {d.offer_id for d in decisions if d.id in applied}
        return {
            offer_id: (status_by_offer.get(offer_id), offer_id in applied_offer_ids)
            for offer_id in self.recommendations.offer_ids()
        }

    def candidate_activity(
        self,
        candidate_id: str,
        *,
        limit: int = 20,
        offer_limit: int = 5,
        letters_at: Callable[[list[str]], dict[str, str]] | None = None,
        applied_at: Callable[[list[str]], dict[str, str]] | None = None,
    ) -> list[ActivityEvent]:
        """Flux d'activité récente du candidat pour le cockpit (OPP-165).

        Agrège un journal **transversal** horodaté : décisions tranchées (chaque validation
        humaine de l'historique), lettres de motivation et candidatures déclarées (via les
        résolveurs ``letters_at`` / ``applied_at`` — l'orchestrateur ignore ces services, câblés
        par la couche API), et offres ajoutées au catalogue (pool partagé).

        Les offres du pool sont **plafonnées** à ``offer_limit`` (les plus récentes) *avant* la
        fusion : sinon un catalogue fraîchement alimenté (collecte réelle) noierait les événements
        propres au candidat et les évincerait de la fenêtre ``limit``. Le tout est reclassé du plus
        récent au plus ancien et tronqué à ``limit``.

        Les résolveurs prennent la **liste des ``recommendation_id``** du candidat et rendent une
        table ``{recommendation_id: horodatage}`` (un seul accès par dépôt, pas de N+1). Propage
        ``UnknownCandidateError`` si le candidat est introuvable.
        """
        if self.recommendations.profiles.get(candidate_id) is None:
            raise UnknownCandidateError(f"Candidat introuvable : {candidate_id!r}")

        offers = self.recommendations.offers.list_all()
        title_of = {offer.id: offer.title for offer in offers}

        decisions = self.decisions.list_for_candidate(candidate_id)
        decision_ids = [decision.id for decision in decisions]
        letter_ts = (letters_at or (lambda _ids: {}))(decision_ids)
        applied_ts = (applied_at or (lambda _ids: {}))(decision_ids)

        events: list[ActivityEvent] = []
        for decision in decisions:
            title = title_of.get(decision.offer_id, decision.offer_id)
            for event in decision.history:
                if event.status in HUMAN_STATUSES:
                    events.append(decision_event(event.status, event.at, title, decision.id))
            if letter_ts.get(decision.id):
                events.append(letter_event(letter_ts[decision.id], title, decision.id))
            if applied_ts.get(decision.id):
                events.append(application_event(applied_ts[decision.id], title, decision.id))

        offer_events = [offer_event(offer.created_at, offer.title, offer.id) for offer in offers]
        events.extend(most_recent(offer_events, limit=offer_limit))

        return most_recent(events, limit=limit)

    def _execute(
        self,
        candidate_id: str,
        recommendations: list[OfferRecommendation],
    ) -> tuple[HermesRun, list[OfferRecommendation]]:
        """Persiste une décision par recommandation en journalisant l'exécution.

        Chaque erreur **par offre** est capturée dans le run et n'interrompt pas les
        suivantes (reprise idempotente à l'exécution suivante). Retourne le run — persisté
        si un dépôt ``runs`` est configuré — et la sous-liste des recommandations
        effectivement persistées (offres en erreur exclues).
        """
        run_id = self._run_id()
        executed_at = self._now()

        evaluations: list[OfferEvaluation] = []
        errors: list[str] = []
        persisted: list[OfferRecommendation] = []
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
            # Snapshot riche figé au run-time (cf. OfferEvaluation) : pré-éval automatique
            # (advisory_status/action) + contexte offre, pour une restitution paginée stable
            # sans re-dérouler le pipeline. ``decision_status`` est la photo initiale ; l'état
            # humain courant est relu en direct par ``get_run_recommendation_items``.
            advisory_status = self.decisions.evaluate(recommendation).status
            evaluations.append(
                OfferEvaluation(
                    offer_id=offer_id,
                    score=recommendation.score,
                    decision_status=decision.status,
                    advisory_status=advisory_status,
                    action=recommendation.action,
                    title=recommendation.offer.title,
                    company=recommendation.offer.company,
                    justification=recommendation.justification,
                )
            )
            persisted.append(recommendation)

        run = HermesRun(
            run_id=run_id,
            candidate_id=candidate_id,
            executed_at=executed_at,
            evaluations=tuple(evaluations),
            errors=tuple(errors),
        )
        # Un run **vraiment vide** (aucune évaluation *et* aucune erreur) ne porte aucune
        # information : avec ``only_new`` (OPP-150), relancer une analyse sans nouvelle offre
        # en produirait un à chaque clic, polluant la liste des runs. On ne le persiste donc
        # pas — l'appelant reçoit tout de même l'objet (``run_id`` sans ressource côté dépôt,
        # cf. le front qui n'y navigue pas). Un run avec des erreurs par offre reste persisté.
        if self.runs is not None and (evaluations or errors):
            self.runs.save(run)
        return run, persisted

    def _bucket(
        self,
        candidate_id: str,
        recommendations: list[OfferRecommendation],
    ) -> dict:
        """Trie des recommandations par statut de **pré-évaluation automatique**.

        Délègue le triage à ``DecisionService.evaluate`` (pur, sans persistance) et
        regroupe par statut, en préservant l'ordre de classement au sein de chaque groupe.
        """
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

    # --- Consultation et décision humaine (adressées par identifiant) -------------

    def get_run(self, run_id: str) -> HermesRun | None:
        """Retourne l'exécution journalisée d'``run_id``, ou ``None`` (dépôt absent inclus)."""
        return None if self.runs is None else self.runs.get(run_id)

    def delete_run(self, run_id: str) -> bool:
        """Supprime une exécution journalisée ; ``True`` si retirée (OPP-144).

        ``False`` si le dépôt est absent ou le run inconnu. Les décisions persistées ne
        sont pas touchées (elles vivent dans ``DecisionStore``).
        """
        return False if self.runs is None else self.runs.delete(run_id)

    def list_run_summaries(
        self,
        candidate_ids: Collection[str] | None = None,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[HermesRunSummary], int]:
        """Résumés **paginés** des runs du périmètre + total ; ``([], 0)`` si dépôt absent.

        ``candidate_ids=None`` → tous les runs (mode ouvert) ; sinon restreint au périmètre.
        La pagination (``limit`` / ``offset``) et le comptage sont délégués au dépôt (SQL).
        """
        if self.runs is None:
            return [], 0
        return self.runs.list_run_summaries(candidate_ids, limit=limit, offset=offset)

    def get_run_recommendation_items(
        self,
        run: HermesRun,
        *,
        advisory_status: str | None = None,
        decision_status: str | None = None,
    ) -> list[OfferEvaluation]:
        """Restitue les recommandations **persistées** d'un run, statut humain rafraîchi.

        Le ``run`` déjà chargé est passé par l'appelant (évite une seconde lecture du
        dépôt). Pour chaque offre du run :

        - ``advisory_status`` / ``action`` / ``title`` / ``company`` / ``justification`` /
          ``score`` restent le **snapshot figé** (stable même si l'offre a changé) ;
        - ``decision_status`` est **résolu au courant** : ``DecisionStore`` d'abord, puis
          la valeur du snapshot en **fallback** (décision jamais persistée ou supprimée).

        L'état des décisions est chargé en **une seule** lecture (``list_for_candidate``),
        pas un appel par offre. Les filtres ``advisory_status`` / ``decision_status`` sont
        appliqués **après** résolution du statut courant. L'ordre du run est préservé.
        """
        current = {
            d.offer_id: d.status
            for d in self.decisions.list_for_candidate(run.candidate_id)
        }
        items: list[OfferEvaluation] = []
        for evaluation in run.evaluations:
            live = current.get(evaluation.offer_id, evaluation.decision_status)
            evaluation = replace(evaluation, decision_status=live)
            if advisory_status is not None and evaluation.advisory_status != advisory_status:
                continue
            if decision_status is not None and evaluation.decision_status != decision_status:
                continue
            items.append(evaluation)
        return items

    def get_recommendation(self, recommendation_id: str) -> Decision | None:
        """Retourne la décision (recommandation persistée) d'identifiant donné, ou ``None``.

        ``recommendation_id`` est l'id stable du couple candidat/offre (cf. ``decision_id``).
        """
        return self.decisions.get(recommendation_id)

    def get_offer(self, offer_id: str) -> Offer | None:
        """Retourne l'offre d'``id`` donné, ou ``None`` si absente.

        Sert à enrichir une recommandation (``title``/``company``) pour l'affichage : la
        décision persistée ne porte que l'``offer_id``. ``None`` si l'offre a disparu —
        l'appelant retombe alors sur l'``offer_id`` (cf. OPP-112).
        """
        return self.recommendations.offers.get(offer_id)

    def list_offer_catalog(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        candidate_id: str | None = None,
        stage: str | None = None,
        applied_recommendation_ids: Collection[str] = (),
    ) -> tuple[list[OfferCatalogEntry], int, dict[str, tuple[str | None, bool]]]:
        """Catalogue paginé des offres + score de match + état d'entonnoir pour ``candidate_id``.

        Retourne ``(entrées, total, état d'entonnoir par offre)``. ``total`` est le cardinal
        **du périmètre demandé avant découpe en page** : celui du pool entier sans filtre, ou
        celui du sous-ensemble filtré quand ``stage`` est fourni.

        Filtrage par étape (OPP-164) : quand ``stage`` est une étape d'entonnoir connue et qu'un
        candidat est ciblé, on ne retient que les offres classées à cette étape, **puis** on
        pagine — de sorte que le total (et donc la pagination) concordent avec les compteurs du
        cockpit, même si le pool dépasse une page. Un ``stage`` inconnu (ou sans candidat) est
        ignoré (catalogue complet). Propage ``UnknownCandidateError`` et ``ValueError``.
        """
        if candidate_id is None:
            entries, total = self.recommendations.list_catalog(limit=limit, offset=offset)
            return entries, total, {}

        state = self.funnel_state_by_offer(candidate_id, applied_recommendation_ids)
        if stage not in _FUNNEL_STAGES:
            entries, total = self.recommendations.list_catalog(
                limit=limit, offset=offset, candidate_id=candidate_id
            )
            return entries, total, state

        matching = [
            offer_id
            for offer_id, (status, applied) in state.items()
            if funnel_stage(status, applied) == stage
        ]
        page_ids = matching[offset : offset + limit]
        entries = self.recommendations.catalog_entries_for(page_ids, candidate_id=candidate_id)
        return entries, len(matching), state

    def record_human_decision(
        self, recommendation_id: str, status: str, *, comment: str | None = None
    ) -> Decision:
        """Applique une validation humaine à une recommandation, adressée par son id.

        ``status`` ∈ {``approved``, ``rejected``, ``deferred``}. Délègue à
        ``DecisionService.validate_by_id`` : la décision est persistée et historisée.
        Propage ``UnknownDecisionError`` si l'id est inconnu et ``DecisionError`` si le
        statut n'est pas un statut de validation humaine.
        """
        return self.decisions.validate_by_id(recommendation_id, status, comment=comment)
