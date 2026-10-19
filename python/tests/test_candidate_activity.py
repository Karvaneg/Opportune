"""Tests du flux d'activité (OPP-165) — modèle pur, sans stockage."""

from app.candidate_activity import (
    ActivityEvent,
    application_event,
    decision_event,
    letter_event,
    most_recent,
    offer_event,
)


def test_decision_event_labels_by_status():
    ev = decision_event("approved", "2026-10-01T00:00:00+00:00", "Dev Python", "cand:off")
    assert ev.type == "decision"
    assert ev.label == "Candidature approuvée — Dev Python"
    assert ev.target_kind == "recommendation" and ev.target_id == "cand:off"


def test_rejected_and_deferred_labels():
    assert decision_event("rejected", "t", "X", "r").label.startswith("Offre rejetée")
    assert decision_event("deferred", "t", "X", "r").label.startswith("Décision reportée")


def test_letter_application_offer_events():
    assert letter_event("t", "Dev", "r").type == "letter"
    assert application_event("t", "Dev", "r").label == "Candidature déclarée — Dev"
    o = offer_event("t", "Lead Java", "off-1")
    assert o.type == "offer" and o.target_kind == "offer" and o.target_id == "off-1"


def test_most_recent_sorts_desc_and_truncates():
    events = [
        ActivityEvent("offer", "2026-01-01T00:00:00+00:00", "a", "offer", "1"),
        ActivityEvent("decision", "2026-03-01T00:00:00+00:00", "c", "recommendation", "3"),
        ActivityEvent("letter", "2026-02-01T00:00:00+00:00", "b", "recommendation", "2"),
    ]
    top = most_recent(events, limit=2)
    assert [e.at for e in top] == ["2026-03-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"]


def test_most_recent_empty_limit_is_empty():
    ev = [ActivityEvent("offer", "t", "a", "offer", "1")]
    assert most_recent(ev, limit=0) == []


def test_most_recent_puts_empty_timestamp_last():
    events = [
        ActivityEvent("offer", "", "sans date", "offer", "1"),
        ActivityEvent("decision", "2026-01-01T00:00:00+00:00", "datée", "recommendation", "2"),
    ]
    assert [e.target_id for e in most_recent(events, limit=5)] == ["2", "1"]


def test_most_recent_orders_by_instant_not_text_across_timezones():
    # 08:00 UTC est postérieur à 09:00+02:00 (= 07:00 UTC) : un tri lexicographique inverserait.
    events = [
        ActivityEvent("decision", "2026-01-01T09:00:00+02:00", "plus tôt", "recommendation", "1"),
        ActivityEvent("letter", "2026-01-01T08:00:00+00:00", "plus tard", "recommendation", "2"),
    ]
    assert [e.target_id for e in most_recent(events, limit=5)] == ["2", "1"]
