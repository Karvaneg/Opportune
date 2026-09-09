"""Tests du seuil de recommandation (OPP-0391).

Déterministe, sans LLM ni réseau.
"""

import pytest

from app.candidate_profile import create_profile
from app.offer import Offer
from app.offer_profile_match import (
    ContractMatch,
    LocationMatch,
    OfferProfileMatch,
    SeniorityMatch,
    SkillMatch,
)
from app.offer_recommendation import (
    Recommendation,
    recommend_action,
    recommend_for_match,
    recommend_offer_to_profile,
)


# --- recommend_action --------------------------------------------------------


def test_high_score_recommends_postuler():
    rec = recommend_action(80)
    assert rec.action == "postuler"
    assert rec.label == "Candidater"
    assert rec.score == 80


def test_medium_score_recommends_a_etudier():
    assert recommend_action(60).action == "a_etudier"


def test_low_score_recommends_ignorer():
    assert recommend_action(20).action == "ignorer"


def test_threshold_bounds_are_inclusive():
    # Seuils par défaut alignés sur OPP-003 : postuler ≥ 80, à étudier ≥ 60 (OPP-129).
    assert recommend_action(80).action == "postuler"  # ≥ high
    assert recommend_action(79).action == "a_etudier"  # juste sous high
    assert recommend_action(60).action == "a_etudier"  # ≥ medium
    assert recommend_action(59).action == "ignorer"  # juste sous medium


def test_none_score_is_indeterminee_not_ignorer():
    rec = recommend_action(None)
    assert rec.action == "indeterminee"
    assert rec.score is None


def test_custom_thresholds():
    assert recommend_action(65, high=60, medium=30).action == "postuler"


def test_invalid_thresholds_rejected():
    with pytest.raises(ValueError):
        recommend_action(80, high=40, medium=60)  # medium > high


def test_non_integer_score_rejected():
    with pytest.raises(ValueError):
        recommend_action("80")


def test_bool_score_rejected():
    with pytest.raises(ValueError):
        recommend_action(True)


@pytest.mark.parametrize("score", [-5, 101, 200])
def test_out_of_range_score_rejected(score):
    with pytest.raises(ValueError):
        recommend_action(score)


# --- Raccourcis --------------------------------------------------------------


def _perfect_match() -> OfferProfileMatch:
    return OfferProfileMatch(
        skills=SkillMatch(matched=["Python"], missing=[]),
        contract_type=ContractMatch(offer="CDI", profile="CDI", compatible=True),
        location=LocationMatch(offer="Paris", profile="Paris", status="match"),
        seniority=SeniorityMatch(offer_label="Senior", required_years=5, profile_years=6, status="ok"),
    )


def test_recommend_for_match_postuler():
    assert recommend_for_match(_perfect_match()).action == "postuler"  # score 100


def test_recommend_for_match_indeterminee_when_nothing_evaluable():
    match = OfferProfileMatch(
        skills=SkillMatch(matched=[], missing=[]),
        contract_type=ContractMatch(offer=None, profile=None, compatible=None),
        location=LocationMatch(offer=None, profile=None, status="unknown"),
        seniority=SeniorityMatch(offer_label=None, required_years=None, profile_years=None, status="not_required"),
    )
    assert recommend_for_match(match).action == "indeterminee"


def test_recommend_offer_to_profile_end_to_end():
    offer = Offer(
        id="o-1", title="Dev", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="Backend.", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    profile = create_profile(name="Marie", skills=["Python", "SQL"], contract_type="CDI",
                             location="Paris", total_experience_years=6)
    rec = recommend_offer_to_profile(offer, profile)
    assert isinstance(rec, Recommendation)
    assert rec.action == "postuler"
    assert rec.score == 100
