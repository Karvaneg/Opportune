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
class OfferRecommendation:
    """Une offre recommandée à un candidat, avec sa justification."""

    offer: Offer
    score: int
    action: str  # postuler | a_etudier | ignorer
    matched: list[Reason]  # critères correspondants (points favorables)
    gaps: list[Reason]  # écarts (points défavorables)
    justification: str


def _justify(offer: Offer, score: int, action_label: str, matched: list[Reason], gaps: list[Reason]) -> str:
    """Compose une justification lisible et déterministe."""
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
    masse (``recommend``) et la reco ciblée (``recommend_one``). ``None`` quand le score est
    ``None`` (aucune dimension mesurable) : l'offre n'est alors pas classable.
    """
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

    def recommend(
        self,
        candidate_id: str,
        *,
        limit: int = 10,
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
        - ``limit`` : nombre maximal de recommandations retournées.

        Lève ``UnknownCandidateError`` si le candidat est introuvable, et ``ValueError``
        si ``limit`` est négatif ou les seuils incohérents.
        """
        if limit < 0:
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
            if recommendation is None:  # non évaluable → non classable
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
