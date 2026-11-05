"""Tests du verdict mémoire pour l'avertissement 1er lancement (OPP-193)."""

from app.host_memory import (
    INSUFFICIENT,
    OK,
    TIGHT,
    UNKNOWN,
    assess_memory,
)

_GB = 1024**3


def test_above_recommended_is_ok():
    assert assess_memory(16 * _GB).level == OK


def test_between_minimum_and_recommended_is_tight():
    assert assess_memory(6 * _GB).level == TIGHT


def test_below_minimum_is_insufficient():
    assert assess_memory(2 * _GB).level == INSUFFICIENT


def test_none_is_unknown_not_blocking():
    assessment = assess_memory(None)

    assert assessment.level == UNKNOWN
    assert assessment.total_gb is None


def test_reports_total_in_gb_rounded():
    assert assess_memory(8 * _GB).total_gb == 8.0


def test_custom_thresholds_are_honoured():
    tight = assess_memory(10 * _GB, recommended_gb=12, minimum_gb=4)

    assert tight.level == TIGHT
    assert tight.recommended_gb == 12
