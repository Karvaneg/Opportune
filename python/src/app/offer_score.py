"""Scoring explicable de l'adéquation offre ↔ profil (V2, OPP-039).

Porte en Python le score d'adéquation et son explicabilité (cf. Node
``offerMatchScorer.js`` + ``scoreExplainer.js``) : condense le constat de matching
(``OfferProfileMatch``, OPP-038) en un **score entier 0–100** (ou ``None`` si aucune
dimension n'est évaluable) et des **raisons lisibles**.

Principe : chaque dimension produit un sous-score dans [0,1] (ou ``None`` si non
évaluable) et porte un poids. Le score final est la moyenne pondérée **renormalisée
sur les seules dimensions évaluables** — une dimension inconnue est exclue du calcul
plutôt que comptée comme nulle (on ne pénalise pas ce qu'on ignore). Si **rien** n'est
évaluable, le score vaut ``None`` (« non évaluable »), à ne pas confondre avec un ``0``
(adéquation nulle mais mesurée).

Déterministe, sans LLM ni I/O. Périmètre limité aux dimensions du modèle V2
(compétences, contrat, séniorité, localisation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.candidate_profile import CandidateProfile
from app.offer import Offer
from app.offer_profile_match import (
    ContractMatch,
    LocationMatch,
    OfferProfileMatch,
    SeniorityMatch,
    SkillMatch,
    match_offer_to_profile,
)

# Poids relatifs des dimensions (les compétences priment ; le contrat pèse lourd car
# souvent rédhibitoire). Leur somme vaut 1 quand toutes sont évaluables.
WEIGHTS = {
    "skills": 0.45,
    "contract_type": 0.30,
    "seniority": 0.15,
    "location": 0.10,
}

# Une évaluation de dimension : sous-score dans [0,1] (ou ``None`` si non évaluable) et
# les raisons associées, sous forme de couples ``(impact, message)``. Regrouper score et
# raisons ici évite de dédoubler la correspondance statut → sens (un seul endroit à faire
# évoluer quand une dimension gagne un statut).
_Eval = tuple[float | None, list[tuple[str, str]]]


def _format_years(years: float | None) -> str:
    """Rend un nombre d'années sans décimale superflue (6.0 → « 6 », 6.5 → « 6.5 »)."""
    return "?" if years is None else f"{years:g}"


def _skill_eval(skills: SkillMatch) -> _Eval:
    total = len(skills.matched) + len(skills.missing)
    value = None if total == 0 else len(skills.matched) / total
    reasons: list[tuple[str, str]] = []
    if skills.matched:
        reasons.append(("positive", f"Compétences en adéquation : {', '.join(skills.matched)}"))
    if skills.missing:
        reasons.append(("negative", f"Compétences attendues manquantes : {', '.join(skills.missing)}"))
    return value, reasons


def _contract_eval(contract: ContractMatch) -> _Eval:
    if contract.compatible is True:
        return 1.0, [("positive", f"Type de contrat compatible ({contract.offer})")]
    if contract.compatible is False:
        return 0.0, [("negative", f"Type de contrat non désiré (offre {contract.offer}, profil {contract.profile})")]
    return None, [("unknown", "Type de contrat non évalué")]


def _seniority_eval(seniority: SeniorityMatch) -> _Eval:
    years = _format_years(seniority.profile_years)
    if seniority.status == "ok":
        return 1.0, [("positive", f"Expérience suffisante ({years} ans ≥ {seniority.required_years} requis)")]
    if seniority.status == "insufficient":
        return 0.0, [("negative", f"Expérience insuffisante ({years} ans < {seniority.required_years} requis)")]
    if seniority.status == "not_required":
        return None, []  # pas d'exigence → non discriminant, aucune raison
    return None, [("unknown", "Séniorité non évaluée")]


def _location_eval(location: LocationMatch) -> _Eval:
    if location.status == "match":
        return 1.0, [("positive", f"Lieu correspondant ({location.offer})")]
    if location.status == "not_blocking":
        return 1.0, [("positive", "Lieu non bloquant (profil mobile)")]
    if location.status == "mismatch":
        return 0.0, [("negative", f"Lieu différent (offre {location.offer}, profil {location.profile})")]
    return None, [("unknown", "Lieu non évalué")]


_DIMENSIONS = {
    "skills": _skill_eval,
    "contract_type": _contract_eval,
    "seniority": _seniority_eval,
    "location": _location_eval,
}


@dataclass(frozen=True)
class DimensionScore:
    value: float | None
    weight: float
    evaluated: bool


@dataclass(frozen=True)
class Reason:
    dimension: str
    weight: float
    impact: str  # positive | negative | unknown
    message: str


@dataclass(frozen=True)
class ScoreResult:
    score: int | None  # 0..100, ou None si aucune dimension évaluable
    breakdown: dict[str, DimensionScore]


@dataclass(frozen=True)
class ScoreExplanation:
    score: int | None
    breakdown: dict[str, DimensionScore]
    positives: list[Reason] = field(default_factory=list)
    negatives: list[Reason] = field(default_factory=list)
    unknown: list[Reason] = field(default_factory=list)


def _compute(match: OfferProfileMatch) -> tuple[int | None, dict[str, DimensionScore], list[Reason]]:
    """Évalue chaque dimension une seule fois → score, détail et raisons cohérents."""
    weighted = 0.0
    total_weight = 0.0
    breakdown: dict[str, DimensionScore] = {}
    reasons: list[Reason] = []

    for dimension, evaluate in _DIMENSIONS.items():
        weight = WEIGHTS[dimension]
        value, dim_reasons = evaluate(getattr(match, dimension))
        evaluated = value is not None
        breakdown[dimension] = DimensionScore(value=value, weight=weight, evaluated=evaluated)
        if evaluated:
            weighted += value * weight
            total_weight += weight
        for impact, message in dim_reasons:
            reasons.append(Reason(dimension=dimension, weight=weight, impact=impact, message=message))

    # Non évaluable → None (distinct d'un 0 mesuré). Arrondi au plus proche, moitié vers
    # le haut (``round`` builtin ferait un arrondi au pair, contre-intuitif ici).
    score = None if total_weight == 0 else int(weighted / total_weight * 100 + 0.5)
    return score, breakdown, reasons


def score_match(match: OfferProfileMatch) -> ScoreResult:
    """Calcule le score d'adéquation (0–100, ou None) à partir d'un constat de matching."""
    score, breakdown, _ = _compute(match)
    return ScoreResult(score=score, breakdown=breakdown)


def explain_score(match: OfferProfileMatch) -> ScoreExplanation:
    """Explique le score : raisons positives / négatives / non évaluées, par poids."""
    score, breakdown, all_reasons = _compute(match)

    def by_impact(impact: str) -> list[Reason]:
        selected = [r for r in all_reasons if r.impact == impact]
        return sorted(selected, key=lambda r: r.weight, reverse=True)

    return ScoreExplanation(
        score=score,
        breakdown=breakdown,
        positives=by_impact("positive"),
        negatives=by_impact("negative"),
        unknown=by_impact("unknown"),
    )


# --- Raccourcis ---------------------------------------------------------------


def score_offer_to_profile(offer: Offer, profile: CandidateProfile) -> ScoreResult:
    """Compare l'offre au profil puis calcule le score."""
    return score_match(match_offer_to_profile(offer, profile))


def explain_offer_to_profile(offer: Offer, profile: CandidateProfile) -> ScoreExplanation:
    """Compare l'offre au profil puis explique le score."""
    return explain_score(match_offer_to_profile(offer, profile))
