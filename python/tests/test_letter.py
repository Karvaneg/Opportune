"""Tests du modèle de lettre persistée et de sa validation (OPP-147)."""

import pytest

from app.letter import SOURCE_AI, SOURCE_HUMAN, Letter, LetterError

_BODY = "Corps de lettre suffisamment long pour être plausible et exploitable."


def test_valid_ai_letter():
    letter = Letter(
        recommendation_id="cand-1:off1",
        body=_BODY,
        source=SOURCE_AI,
        model="ministral-3:3b",
        created_at="t0",
        updated_at="t0",
    )
    assert letter.source == "ai"
    assert letter.model == "ministral-3:3b"


def test_valid_human_letter_without_model():
    letter = Letter(recommendation_id="r1", body=_BODY, source=SOURCE_HUMAN)
    assert letter.model == ""  # une édition humaine ne porte pas de modèle


@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
def test_empty_body_rejected(body):
    with pytest.raises(LetterError):
        Letter(recommendation_id="r1", body=body, source=SOURCE_AI)


def test_unknown_source_rejected():
    with pytest.raises(LetterError):
        Letter(recommendation_id="r1", body=_BODY, source="robot")
