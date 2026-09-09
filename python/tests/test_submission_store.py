"""Tests du suivi persistant des soumissions Discord (OPP-131).

SQLite en mémoire, aucun réseau.
"""

import pytest

from app.db import connect
from app.submission_store import Submission, SubmissionStore


@pytest.fixture
def store():
    conn = connect(":memory:")
    yield SubmissionStore(conn)
    conn.close()


def test_unknown_recommendation_has_no_open_submission(store):
    assert store.has_open_submission("cand-1:off-1") is False


def test_record_then_has_open_submission(store):
    store.record("cand-1:off-1", "msg-1", "chan-1", submitted_at="2026-09-09T00:00:00+00:00")

    assert store.has_open_submission("cand-1:off-1") is True
    assert store.get("cand-1:off-1") == Submission(
        recommendation_id="cand-1:off-1", message_id="msg-1", channel_id="chan-1",
        submitted_at="2026-09-09T00:00:00+00:00",
    )


def test_record_is_upsert_on_recommendation_id(store):
    store.record("cand-1:off-1", "msg-1", "chan-1")
    store.record("cand-1:off-1", "msg-2", "chan-1")  # re-soumission → rafraîchit le message

    assert store.count() == 1
    assert store.get("cand-1:off-1").message_id == "msg-2"


def test_forget_allows_resubmission(store):
    store.record("cand-1:off-1", "msg-1", "chan-1")
    store.forget("cand-1:off-1")

    assert store.has_open_submission("cand-1:off-1") is False
    store.forget("cand-1:off-1")  # idempotent : no-op si absente


def test_default_submitted_at_is_stamped(store):
    store.record("cand-1:off-1", "msg-1", "chan-1")  # pas d'horodatage fourni
    assert store.get("cand-1:off-1").submitted_at  # non vide (horodaté par le store)
