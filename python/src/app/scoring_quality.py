"""Qualité du scoring : les offres retenues ont-elles de meilleurs scores ? (OPP-234)

Compare le score des offres que l'utilisateur a **retenues** à celui des offres qu'il a
**rejetées**, d'après ses décisions réelles. Si le score aide à trier, les retenues doivent
avoir en moyenne un meilleur score que les rejetées.

Classement d'une décision :

- **retenue** : offre candidatée, ou décision ``approved`` ;
- **rejetée** : décision ``rejected`` (et offre non candidatée) ;
- ignorée : décision ``pending`` ou ``deferred`` (pas encore tranchée), ou offre sans score
  (formation, OPP-166).

Le score pris en compte est celui de la décision, c'est-à-dire celui que l'utilisateur avait
sous les yeux au moment de décider (il est immuable, cf. ``app.decision``).

Pas de conclusion tant que chaque groupe n'a pas :data:`MIN_PER_GROUP` offres : avec trop peu
de décisions, l'écart des moyennes ne veut rien dire.

Logique pure, sans persistance ni LLM.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.config import RECOMMENDATION_HIGH, RECOMMENDATION_MEDIUM

APPROVED = "approved"
REJECTED = "rejected"

# Nombre minimal d'offres dans **chaque** groupe avant d'afficher une conclusion.
MIN_PER_GROUP = 10

# Verdicts (clés stables, partagées avec le front).
INSUFFICIENT = "insuffisant"
RETAINED_SCORE_HIGHER = "retenues_mieux_notees"
RETAINED_SCORE_NOT_HIGHER = "retenues_pas_mieux_notees"


@dataclass(frozen=True)
class ScoreBands:
    """Nombre d'offres par tranche de score, selon les seuils de la recommandation."""

    high: int  # score ≥ seuil haut (« Candidater »)
    medium: int  # seuil moyen ≤ score < seuil haut (« À étudier »)
    low: int  # score < seuil moyen (« Ignorer »)


@dataclass(frozen=True)
class GroupSummary:
    """Résumé des scores d'un groupe d'offres (retenues ou rejetées)."""

    count: int
    mean: float | None  # arrondie au dixième ; ``None`` si le groupe est vide
    bands: ScoreBands


@dataclass(frozen=True)
class ScoringQuality:
    """Comparaison des scores des offres retenues et rejetées d'une recherche."""

    retained: GroupSummary
    rejected: GroupSummary
    min_per_group: int
    verdict: str  # INSUFFICIENT | RETAINED_SCORE_HIGHER | RETAINED_SCORE_NOT_HIGHER
    # Écart moyenne retenues − moyenne rejetées, calculé sur les moyennes exactes puis arrondi
    # au dixième ; ``None`` si un groupe est vide.
    gap: float | None
    high_threshold: int  # bornes des tranches, pour que l'affichage les cite sans les recopier
    medium_threshold: int


@dataclass(frozen=True)
class DecidedOffer:
    """Ce qu'il faut savoir d'une décision pour la comparaison."""

    score: int | None
    status: str
    applied: bool


def _round_tenth(value: float) -> float:
    """Arrondi au dixième « à la main » (78,25 → 78,3), pas l'arrondi au pair de ``round``."""
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _mean(scores: list[int]) -> float | None:
    return sum(scores) / len(scores) if scores else None


def _summarize(scores: list[int], high: int, medium: int) -> GroupSummary:
    mean = _mean(scores)
    bands = ScoreBands(
        high=sum(1 for s in scores if s >= high),
        medium=sum(1 for s in scores if medium <= s < high),
        low=sum(1 for s in scores if s < medium),
    )
    rounded = _round_tenth(mean) if mean is not None else None
    return GroupSummary(count=len(scores), mean=rounded, bands=bands)


def build_scoring_quality(
    decided: Iterable[DecidedOffer],
    *,
    min_per_group: int = MIN_PER_GROUP,
    high: int = RECOMMENDATION_HIGH,
    medium: int = RECOMMENDATION_MEDIUM,
) -> ScoringQuality:
    """Compare les scores des offres retenues et rejetées (cf. docstring du module)."""
    retained_scores: list[int] = []
    rejected_scores: list[int] = []
    for offer in decided:
        if offer.score is None:
            continue
        if offer.applied or offer.status == APPROVED:
            retained_scores.append(offer.score)
        elif offer.status == REJECTED:
            rejected_scores.append(offer.score)

    # Verdict et écart sur les moyennes exactes : comparer les moyennes arrondies ferait
    # passer un petit écart réel (70,04 contre 70,00) pour une égalité.
    retained_mean = _mean(retained_scores)
    rejected_mean = _mean(rejected_scores)
    if retained_mean is None or rejected_mean is None:
        # Un groupe vide (possible même si ``min_per_group`` vaut 0) : rien à comparer.
        gap = None
        verdict = INSUFFICIENT
    else:
        gap = _round_tenth(retained_mean - rejected_mean)
        if len(retained_scores) < min_per_group or len(rejected_scores) < min_per_group:
            verdict = INSUFFICIENT
        elif retained_mean > rejected_mean:
            verdict = RETAINED_SCORE_HIGHER
        else:
            verdict = RETAINED_SCORE_NOT_HIGHER
    return ScoringQuality(
        retained=_summarize(retained_scores, high, medium),
        rejected=_summarize(rejected_scores, high, medium),
        min_per_group=min_per_group,
        verdict=verdict,
        gap=gap,
        high_threshold=high,
        medium_threshold=medium,
    )
