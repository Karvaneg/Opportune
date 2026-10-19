"""Tests de l'agrégation des stats candidat (OPP-163).

Fonction pure : on construit des recommandations en mémoire, sans aucun stockage.
"""

from app.candidate_stats import CandidateStats, build_candidate_stats
from app.offer import Offer
from app.recommendation_service import OfferRecommendation


def _reco(offer_id: str, action: str, *, kind: str = "emploi") -> OfferRecommendation:
    offer = Offer(
        id=offer_id, title="T", company="C", location="Paris", skills=[],
        seniority="Senior", contract_type="CDI", summary="s", attention_points=[],
        source="indeed", url=f"http://{offer_id}", raw_text="t", kind=kind,
    )
    return OfferRecommendation(
        offer=offer, score=None if action == "indeterminee" else 80,
        action=action, matched=[], gaps=[], justification="j",
    )


def test_counts_by_action_excluding_tranchees():
    recos = [
        _reco("a", "postuler"),
        _reco("b", "postuler"),   # tranchée → exclue
        _reco("c", "a_etudier"),
        _reco("d", "ignorer"),    # jamais compté dans les piles à traiter
    ]
    stats = build_candidate_stats(
        recommendations=recos,
        tranchee_offer_ids={"b"},
        applied_count=2,
        offres_total=5,
    )
    assert stats == CandidateStats(a_etudier=1, a_postuler=1, postule=2, offres_total=5)


def test_empty_pool_is_all_zero():
    stats = build_candidate_stats(
        recommendations=[], tranchee_offer_ids=set(), applied_count=0, offres_total=0
    )
    assert stats == CandidateStats(a_etudier=0, a_postuler=0, postule=0, offres_total=0)


def test_applied_and_total_are_passthrough():
    # postule et offres_total sont fournis par l'appelant (candidatures déclarées, taille pool).
    stats = build_candidate_stats(
        recommendations=[_reco("a", "a_etudier")],
        tranchee_offer_ids=set(),
        applied_count=7,
        offres_total=42,
    )
    assert stats.postule == 7 and stats.offres_total == 42 and stats.a_etudier == 1
