"""Tests des relances côté API (OPP-235) : compteur ``a_relancer`` de ``/stats``, filtre
``?stage=a_relancer`` du catalogue, ``application.follow_up`` du détail, et
``GET|PUT /settings/follow-up``.

Réutilise l'environnement de ``test_api_stats`` (vrais dépôts SQLite en mémoire). Les horloges
de candidature et de suivi y sont figées en septembre 2026 : à la date réelle du test, les délais
de relance sont tous dépassés.
"""

import pytest

from app.decision import decision_id
from app.follow_up_settings_store import FollowUpSettingsStore
from test_api_stats import env  # noqa: F401 - fixture partagée

STATS = "/candidates/cand-1/stats"


def _apply(api, offer_id: str) -> str:
    """Score, approuve et déclare la candidature ; rend le recommendation_id."""
    rid = decision_id("cand-1", offer_id)
    api.dispatch("POST", f"/candidates/cand-1/offers/{offer_id}/rescore", {}, None)
    api.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)
    api.dispatch("POST", f"/applications/{rid}/confirm", {"confirm": True}, None)
    api.dispatch("POST", f"/applications/{rid}/applied", {}, None)
    return rid


def _track(api, rid: str, kind: str, **extra) -> None:
    api.dispatch("POST", f"/applications/{rid}/tracking", {"kind": kind, **extra}, None)


def _follow_up(api, rid: str) -> dict:
    """Relances de la fiche : ``{"due": ..., "next": ...}``."""
    return api.dispatch("GET", f"/recommendations/{rid}", None, None).body["application"][
        "follow_up"
    ]


def test_noted_follow_up_moves_to_the_next_one(env):  # noqa: F811
    rid = _apply(env, "a")
    _track(env, rid, "no_response")

    due = _follow_up(env, rid)["due"]

    assert (due["step"], due["due_date"]) == (2, "2026-09-15")


def test_stats_count_applications_to_follow_up(env):  # noqa: F811
    _apply(env, "a")
    _apply(env, "b")
    _track(env, decision_id("cand-1", "b"), "rejected")

    stats = env.dispatch("GET", STATS, None, None).body

    assert stats["a_relancer"] == 1


def test_catalog_stage_a_relancer_lists_only_applications_to_follow_up(env):  # noqa: F811
    _apply(env, "a")
    _apply(env, "b")
    _track(env, decision_id("cand-1", "b"), "rejected")

    catalog = env.dispatch("GET", "/offers?candidate_id=cand-1&stage=a_relancer", None, None)

    assert [item["id"] for item in catalog.body["items"]] == ["a"]
    assert catalog.body["total"] == 1


def test_recommendation_detail_gives_due_follow_up(env):  # noqa: F811
    rid = _apply(env, "a")

    follow_up = _follow_up(env, rid)

    assert follow_up == {
        "due": {
            "since": "candidature",
            "start_date": "2026-09-05",
            "due_date": "2026-09-13",
            "step": 2,
            "total": 2,
        },
        "next": None,
    }


def test_recommendation_detail_without_application_has_no_follow_up(env):  # noqa: F811
    rid = decision_id("cand-1", "a")
    env.dispatch("POST", "/candidates/cand-1/offers/a/rescore", {}, None)
    env.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)
    env.dispatch("POST", f"/applications/{rid}/confirm", {"confirm": True}, None)

    follow_up = _follow_up(env, rid)

    assert follow_up == {"due": None, "next": None}


def test_rejected_application_has_no_follow_up(env):  # noqa: F811
    rid = _apply(env, "a")
    _track(env, rid, "rejected")

    follow_up = _follow_up(env, rid)

    assert follow_up == {"due": None, "next": None}


def test_approved_but_not_applied_offer_is_not_counted(env):  # noqa: F811
    rid = decision_id("cand-1", "a")
    env.dispatch("POST", "/candidates/cand-1/offers/a/rescore", {}, None)
    env.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)

    stats = env.dispatch("GET", STATS, None, None).body

    assert stats["a_relancer"] == 0


def test_saved_delays_are_used(env, tmp_path):  # noqa: F811
    env.follow_up_settings = FollowUpSettingsStore(tmp_path / "follow_up.json")
    env.dispatch(
        "PUT", "/settings/follow-up", {"after_application": [2], "after_interview": [3]}, None
    )
    rid = _apply(env, "a")

    due = _follow_up(env, rid)["due"]

    assert (due["due_date"], due["total"]) == ("2026-09-07", 1)


def test_settings_default_delays_are_returned(env, tmp_path):  # noqa: F811
    env.follow_up_settings = FollowUpSettingsStore(tmp_path / "follow_up.json")

    resp = env.dispatch("GET", "/settings/follow-up", None, None)

    assert resp.status == 200
    assert resp.body == {"after_application": [5, 8], "after_interview": [5, 8, 15]}


def test_settings_put_returns_saved_delays(env, tmp_path):  # noqa: F811
    env.follow_up_settings = FollowUpSettingsStore(tmp_path / "follow_up.json")
    new_delays = {"after_application": [4, 9], "after_interview": [6, 12, 20]}

    resp = env.dispatch("PUT", "/settings/follow-up", new_delays, None)

    assert resp.status == 200
    assert resp.body == new_delays


@pytest.mark.parametrize(
    "body",
    [
        {"after_application": [8, 5], "after_interview": [5]},
        {"after_application": [5], "after_interview": "5, 8"},
        {"after_interview": [5]},
    ],
)
def test_settings_put_with_invalid_delays_is_400(env, tmp_path, body):  # noqa: F811
    env.follow_up_settings = FollowUpSettingsStore(tmp_path / "follow_up.json")

    resp = env.dispatch("PUT", "/settings/follow-up", body, None)

    assert resp.status == 400


def test_settings_route_without_store_is_404(env):  # noqa: F811
    settings_path = "/settings/follow-up"

    resp = env.dispatch("GET", settings_path, None, None)

    assert resp.status == 404
