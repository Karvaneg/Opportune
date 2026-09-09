"""Tests de la glu décision → lettre → revue Discord (review_pipeline).

Composition réelle des briques MVP, sans réseau : ``LLMRedacteur`` sur ``MockLLMClient``
et ``DiscordReviewer`` sur ``MockDiscordTransport``.
"""

import pytest

from app.decision import create_decision
from app.discord_review import DiscordReviewer, encode_custom_id
from app.discord_transport import MockDiscordTransport
from app.llm_client import LLMError, MockLLMClient
from app.offer import Offer
from app.redacteur import LLMRedacteur
from app.decision import validate
from app.review_pipeline import (
    BatchReviewError,
    ReviewedCandidature,
    only_unsubmitted,
    prepare_and_submit_review,
    submit_pending_reviews,
)
from app.submission_store import SubmissionStore
from app.db import connect

LETTER = ("Madame, Monsieur, " + "texte de motivation " * 15).strip()


def _offer(offer_id: str = "abc123def456", **overrides) -> Offer:
    data = dict(
        id=offer_id,
        title="Développeuse Python",
        company="Acme",
        location="Paris",
        skills=["Python"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend data.",
        attention_points=[],
        source="collée",
        url="",
        raw_text="...",
    )
    data.update(overrides)
    return Offer(**data)


def _profile():
    from app.candidate_profile import create_profile

    return create_profile(name="Marie", skills=["Python"], contract_type="CDI")


def _decision(*, offer_id="abc123def456", action="postuler", score=82):
    return create_decision(
        candidate_id="cand-1",
        offer_id=offer_id,
        action=action,
        score=score,
        justification="Bon match",
    )


def _redacteur(letter: str = LETTER):
    return LLMRedacteur(MockLLMClient([letter]))


def _reviewer(**kwargs):
    return DiscordReviewer(MockDiscordTransport(**kwargs), channel_id="chan-1")


# --- prepare_and_submit_review -----------------------------------------------


def test_prepare_and_submit_review_chains_letter_then_push():
    decision = _decision()
    transport = MockDiscordTransport(message_id="msg-9")
    reviewer = DiscordReviewer(transport, channel_id="chan-1")

    result = prepare_and_submit_review(
        decision, _offer(), _profile(), redacteur=_redacteur(), reviewer=reviewer
    )

    assert isinstance(result, ReviewedCandidature)
    assert result.recommendation_id == decision.id
    assert result.cover_letter.body == LETTER
    assert result.submission.message_id == "msg-9"

    # Le message poussé porte la lettre et les boutons de la bonne recommandation.
    sent = transport.sent[0]["message"]
    assert sent["embeds"][0]["description"] == LETTER
    assert sent["components"][0]["components"][0]["custom_id"] == encode_custom_id(
        "approve", decision.id
    )


def test_prepare_and_submit_review_rejects_offer_decision_mismatch():
    decision = _decision(offer_id="abc123def456")
    transport = MockDiscordTransport()
    reviewer = DiscordReviewer(transport, channel_id="chan-1")

    with pytest.raises(ValueError):
        prepare_and_submit_review(
            decision, _offer("autre-offre"), _profile(),
            redacteur=_redacteur(), reviewer=reviewer,
        )
    assert transport.sent == []  # rien poussé sur un décalage d'offre


def test_prepare_and_submit_review_does_not_push_when_letter_fails():
    # Le moteur lève : aucune lettre, donc aucun message Discord.
    redacteur = LLMRedacteur(MockLLMClient(error=LLMError("réseau")))
    transport = MockDiscordTransport()
    reviewer = DiscordReviewer(transport, channel_id="chan-1")

    with pytest.raises(LLMError):
        prepare_and_submit_review(
            _decision(), _offer(), _profile(), redacteur=redacteur, reviewer=reviewer
        )
    assert transport.sent == []


# --- only_unsubmitted (idempotence, OPP-131) ---------------------------------


def test_only_unsubmitted_excludes_already_submitted():
    conn = connect(":memory:")
    submissions = SubmissionStore(conn)
    decision = _decision(offer_id="off-a", action="postuler")
    guard = only_unsubmitted(submissions)

    assert guard(decision) is True  # jamais soumise → éligible
    submissions.record(decision.id, "msg-1", "chan-1")
    assert guard(decision) is False  # déjà une carte vivante → écartée
    conn.close()


def test_only_unsubmitted_keeps_base_eligibility():
    conn = connect(":memory:")
    guard = only_unsubmitted(SubmissionStore(conn))
    # Non éligible au départ (a_etudier) : le suivi ne l'ouvre pas.
    assert guard(_decision(offer_id="off-b", action="a_etudier")) is False
    conn.close()


# --- submit_pending_reviews --------------------------------------------------


def test_submit_pending_reviews_only_pushes_eligible_by_default():
    # Par défaut, seules les décisions « postuler » sont poussées.
    postuler = _decision(offer_id="off-a", action="postuler")
    a_etudier = _decision(offer_id="off-b", action="a_etudier")
    items = [(postuler, _offer("off-a")), (a_etudier, _offer("off-b"))]
    transport = MockDiscordTransport()
    reviewer = DiscordReviewer(transport, channel_id="chan-1")

    results = submit_pending_reviews(
        items, _profile(),
        redacteur=LLMRedacteur(MockLLMClient([LETTER, LETTER])),
        reviewer=reviewer,
    )

    assert [r.recommendation_id for r in results] == [postuler.id]
    assert len(transport.sent) == 1


def test_submit_pending_reviews_skips_already_decided_by_default():
    # Une décision « postuler » déjà tranchée par un humain (status ≠ pending) n'est
    # pas re-poussée : le prédicat par défaut est sûr aux re-runs.
    pending = _decision(offer_id="off-a", action="postuler")
    decided = validate(_decision(offer_id="off-b", action="postuler"), "approved")
    items = [(pending, _offer("off-a")), (decided, _offer("off-b"))]
    transport = MockDiscordTransport()
    reviewer = DiscordReviewer(transport, channel_id="chan-1")

    results = submit_pending_reviews(
        items, _profile(),
        redacteur=LLMRedacteur(MockLLMClient([LETTER, LETTER])),
        reviewer=reviewer,
    )

    assert [r.recommendation_id for r in results] == [pending.id]
    assert len(transport.sent) == 1


def test_submit_pending_reviews_reports_progress_on_failure():
    # Le 2e item échoue (plus de lettre scriptée) : le 1er reste poussé et la
    # BatchReviewError porte la frontière poussé/non-poussé pour une reprise sans doublon.
    d1 = _decision(offer_id="off-a", action="postuler")
    d2 = _decision(offer_id="off-b", action="postuler")
    items = [(d1, _offer("off-a")), (d2, _offer("off-b"))]
    transport = MockDiscordTransport()
    reviewer = DiscordReviewer(transport, channel_id="chan-1")

    with pytest.raises(BatchReviewError) as exc_info:
        submit_pending_reviews(
            items, _profile(),
            redacteur=LLMRedacteur(MockLLMClient([LETTER])),  # une seule lettre
            reviewer=reviewer,
        )

    err = exc_info.value
    assert [r.recommendation_id for r in err.results] == [d1.id]  # 1er poussé
    assert err.failed is d2
    assert err.__cause__ is not None  # cause d'origine chaînée
    assert len(transport.sent) == 1  # aucun push pour le dossier fautif


def test_submit_pending_reviews_honours_custom_predicate_and_order():
    d1 = _decision(offer_id="off-a", action="a_etudier")
    d2 = _decision(offer_id="off-b", action="ignorer")
    items = [(d1, _offer("off-a")), (d2, _offer("off-b"))]
    reviewer = _reviewer()

    results = submit_pending_reviews(
        items, _profile(),
        redacteur=LLMRedacteur(MockLLMClient([LETTER, LETTER])),
        reviewer=reviewer,
        should_review=lambda d: True,  # tout pousser
    )

    assert [r.recommendation_id for r in results] == [d1.id, d2.id]  # ordre préservé
