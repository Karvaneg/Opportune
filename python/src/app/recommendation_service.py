"""Service de recommandation d'opportunités (V2, OPP-0393).

Orchestre les briques d'analyse V2 pour, d'un **candidat**, produire les **meilleures
offres** du stock, classées et justifiées :

    profil (ProfileStore) → offres (OfferStore) → matching → scoring
        → filtrage (min_score) → tri (date décroissante, OPP-152) → top N

Distinct du pipeline d'ingestion (OPP-0392) : celui-ci n'analyse rien, il exploite les
offres déjà stockées. Le score est **relatif au candidat**, donc recalculé à chaque
appel. Déterministe, sans LLM ni réseau ; les dépôts sont injectés (protocoles).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.candidate_profile import CandidateProfile
from app.offer import Offer
from app.offer_kind import FORMATION
from app.offer_profile_match import match_offer_to_profile
from app.offer_score import Reason, explain_score
from app.offer_recommendation import (
    DEFAULT_HIGH,
    DEFAULT_MEDIUM,
    recommend_action,
    validate_thresholds,
)


class ProfileSource(Protocol):
    def get(self, profile_id: str) -> CandidateProfile | None: ...


class OfferSource(Protocol):
    def list_all(self) -> list[Offer]: ...

    def list(self, *, limit: int, offset: int = 0) -> list[Offer]: ...

    def count(self) -> int: ...

    def get(self, offer_id: str) -> Offer | None: ...


class UnknownCandidateError(Exception):
    """Aucun profil candidat ne correspond à l'``candidate_id`` fourni."""


def _matches_filters(
    offer: Offer, contract_type: str | None, skills: list[str]
) -> bool:
    """Filtre déterministe appliqué **avant** le classement (donc avant ``limit``).

    - ``contract_type`` : correspondance exacte au type (déjà normalisé) de l'offre ;
      ``None`` = pas de contrainte.
    - ``skills`` : sémantique **ALL** — l'offre doit mentionner *toutes* les compétences
      demandées (comparaison insensible à la casse) ; liste vide = pas de contrainte.
    """
    if contract_type is not None and offer.contract_type != contract_type:
        return False
    if skills:
        owned = {s.lower() for s in offer.skills}
        if not all(s.lower() in owned for s in skills):
            return False
    return True


@dataclass(frozen=True)
class OfferCatalogEntry:
    """Une offre du catalogue, avec son score de match pour un candidat (OPP-146).

    ``score`` est ``None`` quand aucun candidat n'est demandé (catalogue brut) **ou** quand
    l'offre n'est pas évaluable pour ce candidat (aucune dimension mesurable). ``action`` est
    la bande recommandée pour ce score (``postuler``/``a_etudier``/``ignorer``), ``None`` dans
    les mêmes cas que ``score`` — c'est elle (et non un seuil recalculé côté client) qui dicte
    l'affichage, pour que front et back partagent une **unique** source de vérité des seuils.
    """

    offer: Offer
    score: int | None
    action: str | None


@dataclass(frozen=True)
class OfferRecommendation:
    """Une offre recommandée à un candidat, avec sa justification.

    ``score`` vaut ``None`` pour une **formation** (OPP-166) : on ne mesure pas l'adéquation
    d'un cursus (son but est d'acquérir les compétences). Elle reste néanmoins une
    recommandation à part entière — ouvrable en fiche, décidable, avec lettre — car se
    former peut être une candidature. ``action`` est alors ``indeterminee`` (aucune
    pré-reco automatique).
    """

    offer: Offer
    score: int | None
    action: str  # postuler | a_etudier | ignorer | indeterminee
    matched: list[Reason]  # critères correspondants (points favorables)
    gaps: list[Reason]  # écarts (points défavorables)
    justification: str


def _justify(offer: Offer, score: int | None, action_label: str, matched: list[Reason], gaps: list[Reason]) -> str:
    """Compose une justification lisible et déterministe.

    Pour une formation (``score`` ``None``), on n'affiche pas de score d'adéquation : la
    justification explique que le score ne s'applique pas à un cursus.
    """
    if score is None:
        return (
            f"Formation ({offer.title}) : l'adéquation n'est pas évaluée — un cursus vise à "
            "acquérir des compétences, pas à en exiger. À toi de décider de candidater."
        )
    parts = [f"Score {score}/100 — {action_label} ({offer.title})."]
    if matched:
        parts.append("Atouts : " + " ; ".join(r.message for r in matched) + ".")
    if gaps:
        parts.append("Écarts : " + " ; ".join(r.message for r in gaps) + ".")
    return " ".join(parts)


def _evaluate_offer(
    offer: Offer, profile: CandidateProfile, *, high: int, medium: int
) -> OfferRecommendation | None:
    """Score **une** offre pour un profil → ``OfferRecommendation``, ou ``None`` si non évaluable.

    Source unique du scoring + construction de la recommandation, partagée par la reco de
    masse (``recommend``) et la reco ciblée (``recommend_one``).

    Deux cas de non-scoring, traités différemment :
    - une **formation** (OPP-166) : on ne la score pas comme un emploi (ses compétences sont
      le but, pas un prérequis), mais elle reste une recommandation à part entière (score
      ``None``, action ``indeterminee``) — se former peut être une candidature, donc sa fiche
      s'ouvre et se décide. Elle est seulement écartée du **classement** (``recommend``) ;
    - un **emploi non évaluable** (aucune dimension mesurable, score ``None``) : ``None`` pur,
      non classable et sans fiche.
    """
    if offer.kind == FORMATION:
        action = recommend_action(None, high=high, medium=medium)  # -> indeterminee
        return OfferRecommendation(
            offer=offer,
            score=None,
            action=action.action,
            matched=[],
            gaps=[],
            justification=_justify(offer, None, action.label, [], []),
        )
    explanation = explain_score(match_offer_to_profile(offer, profile))
    score = explanation.score
    if score is None:
        return None
    action = recommend_action(score, high=high, medium=medium)
    return OfferRecommendation(
        offer=offer,
        score=score,
        action=action.action,
        matched=explanation.positives,
        gaps=explanation.negatives,
        justification=_justify(offer, score, action.label, explanation.positives, explanation.negatives),
    )


class RecommendationService:
    """Recommande les meilleures offres du stock pour un candidat donné."""

    def __init__(self, profiles: ProfileSource, offers: OfferSource) -> None:
        self.profiles = profiles
        self.offers = offers

    def pool_size(self) -> int:
        """Nombre total d'offres du pool partagé (toutes offres, formations comprises).

        Sert au ``offres_total`` des agrégats du cockpit (OPP-163) — à distinguer du nombre
        d'offres *scorées* (``recommend`` exclut formations et offres non évaluables).
        """
        return self.offers.count()

    def offer_ids(self) -> list[str]:
        """Identifiants de **toutes** les offres du pool partagé (ordre du dépôt).

        Sert à l'entonnoir du cockpit (OPP-163/164), qui classe chaque offre du pool selon la
        décision/candidature du candidat — indépendamment du score de l'algo.
        """
        return [offer.id for offer in self.offers.list_all()]

    def recommend(
        self,
        candidate_id: str,
        *,
        limit: int | None = 10,
        min_score: int | None = None,
        high: int = DEFAULT_HIGH,
        medium: int = DEFAULT_MEDIUM,
        filters: dict | None = None,
        exclude_offer_ids: set[str] | None = None,
    ) -> list[OfferRecommendation]:
        """Retourne les offres recommandées au candidat, classées **par date décroissante**.

        - ``min_score`` : seuil d'inclusion ; les offres en dessous sont écartées.
        - ``filters`` (optionnel) : restreint le stock **avant** scoring et coupe ``limit``,
          via ``contract_type`` (correspondance exacte) et ``skills`` (sémantique ALL). La
          normalisation/validation des valeurs incombe à l'appelant ; ici on applique un
          dict déjà propre ``{"contract_type": str | None, "skills": list[str]}``.
        - ``exclude_offer_ids`` (optionnel) : ids d'offres à **ignorer** avant tout scoring —
          sert à ne (re)traiter que les offres « nouvelles » (cf. OPP-150 : un run n'évalue
          que celles sans décision déjà posée pour le candidat).
        - Les offres **non évaluables** (score ``None``, aucune dimension mesurable)
          sont exclues du classement.
        - ``limit`` : nombre maximal de recommandations retournées ; ``None`` = **toutes**
          (sans troncature — utile pour des agrégats globaux, cf. ``HermesOrchestrator``).

        Lève ``UnknownCandidateError`` si le candidat est introuvable, et ``ValueError``
        si ``limit`` est négatif ou les seuils incohérents.
        """
        if limit is not None and limit < 0:
            raise ValueError("limit doit être ≥ 0")
        validate_thresholds(high, medium)

        profile = self.profiles.get(candidate_id)
        if profile is None:
            raise UnknownCandidateError(f"Candidat introuvable : {candidate_id!r}")

        contract_type = (filters or {}).get("contract_type")
        skills = (filters or {}).get("skills") or []

        recommendations: list[OfferRecommendation] = []
        for offer in self.offers.list_all():
            if exclude_offer_ids and offer.id in exclude_offer_ids:
                continue
            if not _matches_filters(offer, contract_type, skills):
                continue
            recommendation = _evaluate_offer(offer, profile, high=high, medium=medium)
            # Non classable : emploi non évaluable (``None``) ou formation (score ``None``, non
            # scorée). Les formations restent ouvrables en fiche via ``recommend_one``, mais
            # n'ont pas leur place dans un classement de masse (rien à ranger).
            if recommendation is None or recommendation.score is None:
                continue
            if min_score is not None and recommendation.score < min_score:
                continue
            recommendations.append(recommendation)

        # Tri par date d'ingestion décroissante (plus récentes d'abord, OPP-152) — et non
        # par score : le score reste calculé et affiché, mais ne gouverne plus l'ordre.
        # Tri explicite ici (et non délégué à ``list_all``) : le protocole ``OfferSource`` ne
        # garantit aucun ordre. Deux passes stables : titre/id ascendants (tie-break), puis
        # date descendante (``reverse=True`` préserve la stabilité des ex æquo).
        recommendations.sort(key=lambda r: (r.offer.title, r.offer.id))
        recommendations.sort(key=lambda r: r.offer.created_at, reverse=True)
        return recommendations[:limit]

    def recommend_one(
        self,
        candidate_id: str,
        offer_id: str,
        *,
        high: int = DEFAULT_HIGH,
        medium: int = DEFAULT_MEDIUM,
    ) -> OfferRecommendation | None:
        """Recommande **une** offre précise pour un candidat (re-score ciblé, OPP-150).

        Retourne ``None`` si l'offre est introuvable **ou** non évaluable (score ``None``).
        Lève ``UnknownCandidateError`` si le candidat est introuvable et ``ValueError`` si
        les seuils sont incohérents — même contrat que ``recommend``.
        """
        validate_thresholds(high, medium)
        profile = self.profiles.get(candidate_id)
        if profile is None:
            raise UnknownCandidateError(f"Candidat introuvable : {candidate_id!r}")
        offer = self.offers.get(offer_id)
        if offer is None:
            return None
        return _evaluate_offer(offer, profile, high=high, medium=medium)

    def list_catalog(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        candidate_id: str | None = None,
        high: int = DEFAULT_HIGH,
        medium: int = DEFAULT_MEDIUM,
    ) -> tuple[list[OfferCatalogEntry], int]:
        """Catalogue paginé des offres (plus récentes d'abord) + leur score de match (OPP-146).

        Distinct de ``recommend`` : ici on liste **toutes** les offres de la page sans
        filtrage ni reclassement par score, et on **annote** chacune de son score pour
        ``candidate_id`` (ou ``None`` si non évaluable, ou si aucun candidat n'est demandé).
        Retourne ``(entrées, total)`` — ``total`` est le cardinal **avant** découpe en page.

        Lève ``ValueError`` si ``limit``/``offset`` sont négatifs ou les seuils incohérents.
        N'exige **pas** de profil : un ``candidate_id`` sans profil (« nouveau profil ») donne
        des offres **sans score annoté** (``None``), pas une erreur (cf. ``_resolve_profile``).
        """
        if limit < 0 or offset < 0:
            raise ValueError("limit et offset doivent être ≥ 0")
        validate_thresholds(high, medium)

        profile = self._resolve_profile(candidate_id)
        entries = [
            self._catalog_entry(offer, profile, high=high, medium=medium)
            for offer in self.offers.list(limit=limit, offset=offset)
        ]
        return entries, self.offers.count()

    def catalog_entries_for(
        self,
        offer_ids: list[str],
        *,
        candidate_id: str | None = None,
        high: int = DEFAULT_HIGH,
        medium: int = DEFAULT_MEDIUM,
    ) -> list[OfferCatalogEntry]:
        """Entrées de catalogue pour une **liste d'offres déjà sélectionnée**, dans l'ordre fourni.

        Variante de ``list_catalog`` quand le filtrage et la pagination sont faits en amont
        (p. ex. filtre par étape d'entonnoir côté serveur, OPP-164) : même annotation de score,
        mais sans re-trancher ni re-paginer. Les ``offer_ids`` introuvables sont ignorés.

        N'exige **pas** de profil (comme ``list_catalog``) : un ``candidate_id`` sans profil
        donne des offres **sans score annoté** (``None``), pas une erreur.
        """
        validate_thresholds(high, medium)
        profile = self._resolve_profile(candidate_id)
        entries: list[OfferCatalogEntry] = []
        for offer_id in offer_ids:
            offer = self.offers.get(offer_id)
            if offer is None:
                continue
            entries.append(self._catalog_entry(offer, profile, high=high, medium=medium))
        return entries

    def _resolve_profile(self, candidate_id: str | None):
        """Profil à utiliser pour **annoter** le catalogue, ou ``None`` → scores non annotés.

        ``None`` dans deux cas, traités pareil (score ``null``) : aucun candidat demandé, **ou**
        candidat ciblé encore **sans profil** (« nouveau profil »). On ne lève pas : lister le
        catalogue n'exige pas de profil (seul le **score** en a besoin), et le périmètre est déjà
        garanti en amont (owner-gating de l'API). Le scoring explicite (``recommend`` /
        ``recommend_one``), lui, continue d'exiger un profil et lève ``UnknownCandidateError``.
        """
        if candidate_id is None:
            return None
        return self.profiles.get(candidate_id)  # None si pas de profil → offres sans score

    def _catalog_entry(
        self, offer: Offer, profile, *, high: int, medium: int
    ) -> OfferCatalogEntry:
        """Annote une offre de son score/bande pour ``profile`` (ou ``None`` sans candidat).

        On n'annote que sur un score mesuré : une formation (score ``None``) reste sans score
        ni bande au catalogue (le front la badge via ``offer.kind``).
        """
        score: int | None = None
        action: str | None = None
        if profile is not None:
            recommendation = _evaluate_offer(offer, profile, high=high, medium=medium)
            if recommendation is not None and recommendation.score is not None:
                score = recommendation.score
                action = recommendation.action
        return OfferCatalogEntry(offer=offer, score=score, action=action)
