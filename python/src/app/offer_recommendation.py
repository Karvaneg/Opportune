"""Seuil de recommandation (V2, OPP-0391).

Porte en Python le seuil de recommandation (cf. Node ``scoreRecommender.js``) : à partir
du score d'adéquation (0–100, ou ``None``), recommande une action. Déterministe, seuils
configurables.

Nouveauté V2 : le score peut valoir ``None`` (aucune dimension évaluable, cf. OPP-039).
Ce cas produit une action dédiée ``indeterminee`` — jamais confondu avec ``ignorer``
(qui, lui, résulte d'un score bas *mesuré*).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.candidate_profile import CandidateProfile
from app.offer import Offer
from app.offer_profile_match import OfferProfileMatch, match_offer_to_profile
from app.offer_score import score_match

# Seuils par défaut (bornes basses incluses) : score ≥ high → postuler,
# score ≥ medium → à étudier, sinon → ignorer.
DEFAULT_HIGH = 75
DEFAULT_MEDIUM = 50

# Codes d'action stables (exploitables) + libellés affichables.
_LABELS = {
    "postuler": "Candidater",
    "a_etudier": "À étudier",
    "ignorer": "Ignorer",
    "indeterminee": "À évaluer (données insuffisantes)",
}


@dataclass(frozen=True)
class Recommendation:
    action: str  # postuler | a_etudier | ignorer | indeterminee
    label: str
    score: int | None


def validate_thresholds(high: int, medium: int) -> None:
    """Vérifie la cohérence des seuils (``0 ≤ medium ≤ high ≤ 100``) ; ``ValueError`` sinon.

    Exposé pour que les appelants (p. ex. le pipeline) puissent échouer *avant* tout
    effet de bord, sans dupliquer la contrainte.
    """
    if not (0 <= medium <= high <= 100):
        raise ValueError("Seuils invalides : attendu 0 ≤ medium ≤ high ≤ 100")


def recommend_action(
    score: int | None, *, high: int = DEFAULT_HIGH, medium: int = DEFAULT_MEDIUM
) -> Recommendation:
    """Recommande une action selon un ``score``.

    ``score=None`` → ``indeterminee``. Lève ``ValueError`` si le score n'est ni un
    entier ni ``None``, ou si les seuils sont incohérents (``0 ≤ medium ≤ high ≤ 100``).
    """
    validate_thresholds(high, medium)

    if score is None:
        return Recommendation("indeterminee", _LABELS["indeterminee"], None)

    # bool est un int en Python : on l'exclut explicitement d'un score valide.
    if isinstance(score, bool) or not isinstance(score, int):
        raise ValueError("recommend_action : le score doit être un entier ou None")
    if not (0 <= score <= 100):
        raise ValueError("recommend_action : le score doit être dans [0, 100]")

    if score >= high:
        action = "postuler"
    elif score >= medium:
        action = "a_etudier"
    else:
        action = "ignorer"
    return Recommendation(action, _LABELS[action], score)


def recommend_for_match(
    match: OfferProfileMatch, *, high: int = DEFAULT_HIGH, medium: int = DEFAULT_MEDIUM
) -> Recommendation:
    """Calcule le score d'un constat de matching puis recommande une action."""
    return recommend_action(score_match(match).score, high=high, medium=medium)


def recommend_offer_to_profile(
    offer: Offer,
    profile: CandidateProfile,
    *,
    high: int = DEFAULT_HIGH,
    medium: int = DEFAULT_MEDIUM,
) -> Recommendation:
    """Compare l'offre au profil, score, puis recommande une action (bout en bout)."""
    return recommend_for_match(match_offer_to_profile(offer, profile), high=high, medium=medium)
