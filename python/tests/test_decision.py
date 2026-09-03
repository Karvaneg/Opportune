"""Tests du modèle de décision et de sa validation humaine (OPP-057)."""

import pytest

from app.decision import (
    HUMAN_STATUSES,
    PENDING,
    Decision,
    DecisionError,
    create_decision,
    decision_from_recommendation,
    validate,
)

# Horloge déterministe : chaque appel renvoie l'instant suivant.
class _FakeClock:
    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"t{self.n}"


def _decision(now=None) -> Decision:
    return create_decision(
        candidate_id="cand-1", offer_id="off-1", action="postuler",
        score=90, justification="Score 90/100.", now=now or (lambda: "t0"),
    )


def test_create_decision_starts_pending_with_history():
    d = _decision()
    assert d.status == PENDING
    assert d.id == "cand-1:off-1"
    assert d.action == "postuler"
    assert d.score == 90
    assert len(d.history) == 1
    assert d.history[0].status == PENDING
    assert d.history[0].at == "t0"


def test_validate_approved_records_history_and_keeps_original():
    clock = _FakeClock()
    d = create_decision(
        candidate_id="c", offer_id="o", action="postuler", score=90,
        justification="Score 90/100.", now=clock,
    )
    approved = validate(d, "approved", comment="OK pour moi", now=clock)

    assert approved.status == "approved"
    assert approved.comment == "OK pour moi"
    assert len(approved.history) == 2
    assert approved.history[-1].status == "approved"
    assert approved.history[-1].comment == "OK pour moi"
    # recommandation d'origine préservée
    assert approved.action == "postuler"
    assert approved.score == 90
    assert approved.justification == "Score 90/100."
    # immuabilité de l'original
    assert d.status == PENDING
    assert len(d.history) == 1


def test_validate_rejects_invalid_status():
    with pytest.raises(DecisionError):
        validate(_decision(), "pending")  # on ne revient jamais à pending
    with pytest.raises(DecisionError):
        validate(_decision(), "n_importe_quoi")


def test_validate_can_be_modified_multiple_times():
    clock = _FakeClock()
    d = create_decision(
        candidate_id="c", offer_id="o", action="a_etudier", score=60,
        justification="Score 60/100.", now=clock,
    )
    deferred = validate(d, "deferred", now=clock)
    approved = validate(deferred, "approved", comment="finalement oui", now=clock)
    assert [e.status for e in approved.history] == [PENDING, "deferred", "approved"]
    assert approved.status == "approved"


def test_human_statuses_are_the_three_expected():
    assert set(HUMAN_STATUSES) == {"approved", "rejected", "deferred"}


def test_decision_from_recommendation_maps_fields():
    class _Offer:
        id = "off-9"

    class _Reco:
        offer = _Offer()
        action = "postuler"
        score = 100
        justification = "Score 100/100 — Candidater."

    d = decision_from_recommendation(_Reco(), "cand-9", now=lambda: "t0")
    assert d.id == "cand-9:off-9"
    assert d.action == "postuler"
    assert d.score == 100
    assert d.justification == "Score 100/100 — Candidater."
    assert d.status == PENDING
