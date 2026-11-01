"""Tests de l'entonnoir d'avancement candidat (OPP-163 / révisé OPP-164).

Fonctions pures : on classe des offres et on agrège, sans aucun stockage.
"""

from datetime import date

from app.application_tracking import create_tracking_event
from app.candidate_stats import (
    CandidateStats,
    build_candidate_stats,
    count_upcoming_interviews,
    funnel_stage,
)


def test_count_upcoming_interviews_counts_today_and_future_only():
    today = date(2026, 11, 1)
    events = [
        create_tracking_event("interview", event_date="2026-11-01", now=lambda: "t"),  # aujourd'hui
        create_tracking_event("interview", event_date="2026-12-15", now=lambda: "t"),  # futur
        create_tracking_event("interview", event_date="2026-10-01", now=lambda: "t"),  # passé
    ]

    assert count_upcoming_interviews(events, today) == 2


def test_count_upcoming_interviews_ignores_dateless_and_non_interviews():
    today = date(2026, 11, 1)
    events = [
        create_tracking_event("interview", now=lambda: "t"),  # entretien sans date prévue
        create_tracking_event("rejected", now=lambda: "t"),  # autre type
        create_tracking_event("offer", now=lambda: "t"),
    ]

    assert count_upcoming_interviews(events, today) == 0


def test_funnel_stage_applied_is_postule_even_if_approved():
    # La candidature prime : une offre candidatée est « postulé », pas « à postuler ».
    assert funnel_stage("approved", True) == "postule"


def test_funnel_stage_approved_not_applied_is_a_postuler():
    assert funnel_stage("approved", False) == "a_postuler"


def test_funnel_stage_pending_or_undecided_is_a_etudier():
    assert funnel_stage("pending", False) == "a_etudier"
    assert funnel_stage(None, False) == "a_etudier"  # pas encore décidée → à étudier


def test_funnel_stage_rejected_or_deferred_is_out():
    assert funnel_stage("rejected", False) is None
    assert funnel_stage("deferred", False) is None


def test_build_counts_each_stage_and_total():
    stages = ["a_etudier", "a_etudier", "a_postuler", "postule", None]  # None = rejetée/reportée
    stats = build_candidate_stats(stages)
    assert stats == CandidateStats(a_etudier=2, a_postuler=1, postule=1, offres_total=5)


def test_build_empty_pool_is_all_zero():
    assert build_candidate_stats([]) == CandidateStats(
        a_etudier=0, a_postuler=0, postule=0, offres_total=0
    )


def test_offres_total_counts_offers_out_of_funnel():
    # Les offres rejetées/reportées (hors entonnoir) comptent quand même dans le total.
    stats = build_candidate_stats([None, None, "a_postuler"])
    assert stats.offres_total == 3 and stats.a_postuler == 1
