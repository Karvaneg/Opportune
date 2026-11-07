"""Tests de la comparaison des scores retenues / rejetées (OPP-234), logique pure."""

from app.scoring_quality import (
    INSUFFICIENT,
    RETAINED_SCORE_HIGHER,
    RETAINED_SCORE_NOT_HIGHER,
    DecidedOffer,
    ScoreBands,
    build_scoring_quality,
)


def _approved(score, applied=False):
    return DecidedOffer(score=score, status="approved", applied=applied)


def _rejected(score):
    return DecidedOffer(score=score, status="rejected", applied=False)


def test_approved_and_applied_offers_are_retained():
    decided = [
        _approved(80),
        DecidedOffer(score=70, status="pending", applied=True),
        _rejected(40),
    ]

    quality = build_scoring_quality(decided, min_per_group=1)

    assert quality.retained.count == 2
    assert quality.rejected.count == 1


def test_applied_offer_counts_as_retained_even_if_rejected_later():
    decided = [DecidedOffer(score=55, status="rejected", applied=True)]

    quality = build_scoring_quality(decided, min_per_group=1)

    assert quality.retained.count == 1
    assert quality.rejected.count == 0


def test_undecided_and_unscored_offers_are_ignored():
    decided = [
        DecidedOffer(score=90, status="pending", applied=False),
        DecidedOffer(score=90, status="deferred", applied=False),
        DecidedOffer(score=None, status="approved", applied=False),
        DecidedOffer(score=None, status="rejected", applied=False),
    ]

    quality = build_scoring_quality(decided)

    assert quality.retained.count == 0
    assert quality.rejected.count == 0
    assert quality.retained.mean is None
    assert quality.rejected.mean is None


def test_means_are_rounded_to_one_decimal():
    decided = [_approved(80), _approved(81), _approved(81), _rejected(50)]

    quality = build_scoring_quality(decided, min_per_group=1)

    assert quality.retained.mean == 80.7
    assert quality.rejected.mean == 50.0


def test_scores_are_split_into_recommendation_bands():
    decided = [_approved(s) for s in (100, 80, 79, 60, 59, 0)]

    quality = build_scoring_quality(decided, min_per_group=1, high=80, medium=60)

    assert quality.retained.bands == ScoreBands(high=2, medium=2, low=2)


def test_verdict_is_insufficient_below_minimum_in_either_group():
    decided = [_approved(90)] * 10 + [_rejected(30)] * 9

    quality = build_scoring_quality(decided, min_per_group=10)

    assert quality.verdict == INSUFFICIENT


def test_verdict_when_retained_offers_score_higher():
    decided = [_approved(85)] * 10 + [_rejected(50)] * 10

    quality = build_scoring_quality(decided, min_per_group=10)

    assert quality.verdict == RETAINED_SCORE_HIGHER


def test_verdict_when_retained_offers_do_not_score_higher():
    decided = [_approved(60)] * 10 + [_rejected(60)] * 10

    quality = build_scoring_quality(decided, min_per_group=10)

    assert quality.verdict == RETAINED_SCORE_NOT_HIGHER


def test_thresholds_are_reported_with_the_result():
    decided: list[DecidedOffer] = []

    quality = build_scoring_quality(decided, min_per_group=10, high=75, medium=50)

    assert (quality.high_threshold, quality.medium_threshold) == (75, 50)
    assert quality.min_per_group == 10


def test_verdict_compares_exact_means_not_rounded_ones():
    # Moyennes exactes 70,01 et 70,0, arrondies à 70,0 toutes les deux : l'écart réel doit
    # quand même donner « mieux notées ».
    decided = [_approved(70)] * 99 + [_approved(71)] + [_rejected(70)] * 100

    quality = build_scoring_quality(decided, min_per_group=10)

    assert quality.retained.mean == quality.rejected.mean == 70.0
    assert quality.verdict == RETAINED_SCORE_HIGHER


def test_gap_is_computed_from_exact_means():
    decided = [_approved(80), _approved(81), _approved(81), _rejected(50)]

    quality = build_scoring_quality(decided, min_per_group=1)

    assert quality.gap == 30.7


def test_gap_is_none_when_a_group_is_empty():
    decided = [_approved(80)]

    quality = build_scoring_quality(decided, min_per_group=1)

    assert quality.gap is None


def test_empty_groups_with_zero_minimum_are_insufficient():
    no_decisions: list[DecidedOffer] = []

    quality = build_scoring_quality(no_decisions, min_per_group=0)

    assert quality.verdict == INSUFFICIENT


def test_half_tenth_rounds_up():
    decided = [_approved(78), _approved(78), _approved(78), _approved(79), _rejected(50)]

    quality = build_scoring_quality(decided, min_per_group=1)

    assert quality.retained.mean == 78.3
