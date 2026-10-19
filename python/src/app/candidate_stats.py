"""Agrégats de décision par candidat, pour le cockpit (V2, OPP-163).

Le catalogue (``GET /offers?candidate_id=``) porte le score et l'action recommandée par
offre, mais **paginé** : impossible d'en dériver des compteurs globaux. Le cockpit a besoin
d'agrégats pré-calculés. ``CandidateStats`` les porte ; ``build_candidate_stats`` les calcule
à partir d'entrées déjà collectées (recommandations live + décisions tranchées + candidatures
déclarées), sans aucun accès au stockage — donc **pure et testable** isolément.

Sémantique retenue (OPP-163) :
- ``a_etudier`` / ``a_postuler`` : offres dont l'action **recommandée** vaut ``a_etudier`` /
  ``postuler`` et dont la décision humaine n'est **pas encore tranchée** (ni approuvée, ni
  rejetée, ni reportée) — ce sont les piles « à traiter », pas une photo figée du pool.
- ``postule`` : candidatures **réellement déclarées** (``applied``), formations comprises.
- ``offres_total`` : taille du pool évalué pour ce candidat (toutes offres, formations
  comprises). Une formation (OPP-166) n'a pas d'action de scoring (``indeterminee``) : elle
  n'entre donc jamais dans ``a_etudier`` / ``a_postuler``, mais compte dans ``offres_total``
  et, si elle est visée, dans ``postule``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.recommendation_service import OfferRecommendation

# Codes d'action recommandée suivis par le cockpit (cf. ``offer_recommendation.ACTION_LABELS``).
_A_ETUDIER = "a_etudier"
_A_POSTULER = "postuler"


@dataclass(frozen=True)
class CandidateStats:
    """Compteurs d'avancement d'un candidat, prêts pour l'accueil cockpit."""

    a_etudier: int
    a_postuler: int
    postule: int
    offres_total: int


def build_candidate_stats(
    *,
    recommendations: list[OfferRecommendation],
    tranchee_offer_ids: set[str],
    applied_count: int,
    offres_total: int,
) -> CandidateStats:
    """Agrège les compteurs du cockpit.

    ``recommendations`` sont les offres **scorées** du pool (emplois ; les formations et les
    offres non évaluables en sont absentes). ``tranchee_offer_ids`` : les offres dont la
    décision humaine est déjà posée (à exclure des piles « à traiter »). ``applied_count`` et
    ``offres_total`` sont fournis par l'appelant (candidatures déclarées, taille du pool).
    """
    a_etudier = 0
    a_postuler = 0
    for reco in recommendations:
        if reco.offer.id in tranchee_offer_ids:
            continue  # décision humaine déjà prise → n'est plus « à traiter »
        if reco.action == _A_ETUDIER:
            a_etudier += 1
        elif reco.action == _A_POSTULER:
            a_postuler += 1
    return CandidateStats(
        a_etudier=a_etudier,
        a_postuler=a_postuler,
        postule=applied_count,
        offres_total=offres_total,
    )
