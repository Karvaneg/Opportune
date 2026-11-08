"""Tests des rappels de relance (OPP-235), logique pure."""

from datetime import date

from app.application_tracking import TrackingEvent
from app.follow_up import (
    SINCE_APPLICATION,
    SINCE_INTERVIEW,
    FollowUpSchedule,
    follow_up_due,
    next_follow_up,
)

APPLIED_AT = "2026-11-01T09:30:00+00:00"
SCHEDULE = FollowUpSchedule(after_application=(5, 8), after_interview=(5, 8, 15))


def _relance(day: str) -> TrackingEvent:
    return TrackingEvent(kind="no_response", at=f"{day}T10:00:00+00:00")


def _interview(day: str) -> TrackingEvent:
    return TrackingEvent(kind="interview", at="2026-11-02T10:00:00+00:00", event_date=day)


def test_no_follow_up_before_first_delay():
    no_events: list[TrackingEvent] = []

    due = follow_up_due(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 5))

    assert due is None


def test_first_follow_up_is_due_five_days_after_application():
    no_events: list[TrackingEvent] = []

    due = follow_up_due(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 6))

    assert due is not None
    assert (due.since, due.step, due.total) == (SINCE_APPLICATION, 1, 2)
    assert due.start_date == date(2026, 11, 1)
    assert due.due_date == date(2026, 11, 6)


def test_second_follow_up_is_due_last_delay_after_the_first():
    one_relance = [_relance("2026-11-06")]

    due_on_day_13 = follow_up_due(APPLIED_AT, one_relance, SCHEDULE, date(2026, 11, 13))
    due_on_day_14 = follow_up_due(APPLIED_AT, one_relance, SCHEDULE, date(2026, 11, 14))

    assert due_on_day_13 is None
    assert due_on_day_14 is not None
    assert (due_on_day_14.step, due_on_day_14.total) == (2, 2)
    assert due_on_day_14.due_date == date(2026, 11, 14)

def test_without_noted_follow_up_the_second_delay_is_the_second_follow_up():
    no_events: list[TrackingEvent] = []

    due = follow_up_due(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 20))

    assert due is not None
    assert (due.step, due.total, due.due_date) == (2, 2, date(2026, 11, 9))


def test_no_follow_up_once_all_application_follow_ups_are_noted():
    two_relances = [_relance("2026-11-06"), _relance("2026-11-09")]

    due = follow_up_due(APPLIED_AT, two_relances, SCHEDULE, date(2026, 12, 31))

    assert due is None


def test_past_interview_restarts_with_interview_delays():
    events = [_relance("2026-11-06"), _relance("2026-11-09"), _interview("2026-11-12")]

    due = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 11, 17))

    assert due is not None
    assert (due.since, due.step, due.total) == (SINCE_INTERVIEW, 1, 3)
    assert due.start_date == date(2026, 11, 12)
    assert due.due_date == date(2026, 11, 17)

def test_second_follow_up_after_interview_is_due_fifteen_days_after_the_first():
    events = [_interview("2026-11-12"), _relance("2026-11-17")]

    due_on_dec_1 = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 12, 1))
    due_on_dec_2 = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 12, 2))

    assert due_on_dec_1 is None
    assert due_on_dec_2 is not None
    assert (due_on_dec_2.since, due_on_dec_2.step) == (SINCE_INTERVIEW, 2)


def test_third_follow_up_after_interview_is_due_fifteen_days_after_the_second():
    events = [_interview("2026-11-12"), _relance("2026-11-17"), _relance("2026-12-02")]

    due_on_dec_16 = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 12, 16))
    due_on_dec_17 = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 12, 17))

    assert due_on_dec_16 is None
    assert due_on_dec_17 is not None
    assert (due_on_dec_17.step, due_on_dec_17.total) == (3, 3)


def test_no_follow_up_once_all_three_interview_follow_ups_are_noted():
    three_relances = [_relance("2026-11-17"), _relance("2026-12-02"), _relance("2026-12-17")]
    events = [_interview("2026-11-12"), *three_relances]

    due = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 12, 31))

    assert due is None

def test_no_follow_up_while_an_interview_is_upcoming():
    upcoming_interview = [_interview("2026-11-30")]

    due = follow_up_due(APPLIED_AT, upcoming_interview, SCHEDULE, date(2026, 11, 20))

    assert due is None


def test_rejection_or_offer_ends_follow_ups():
    rejected = [TrackingEvent(kind="rejected", at="2026-11-03T10:00:00+00:00")]
    offer = [TrackingEvent(kind="offer", at="2026-11-03T10:00:00+00:00")]

    due_after_rejection = follow_up_due(APPLIED_AT, rejected, SCHEDULE, date(2026, 11, 20))
    due_after_offer = follow_up_due(APPLIED_AT, offer, SCHEDULE, date(2026, 11, 20))

    assert due_after_rejection is None
    assert due_after_offer is None


def test_interview_without_planned_date_uses_its_recording_date():
    interview_noted_on_day_3 = [TrackingEvent(kind="interview", at="2026-11-03T10:00:00+00:00")]

    due = follow_up_due(APPLIED_AT, interview_noted_on_day_3, SCHEDULE, date(2026, 11, 8))

    assert due is not None
    assert (due.since, due.due_date) == (SINCE_INTERVIEW, date(2026, 11, 8))


def test_empty_schedule_means_no_follow_up():
    no_follow_up_schedule = FollowUpSchedule(after_application=(), after_interview=())

    due = follow_up_due(APPLIED_AT, [], no_follow_up_schedule, date(2026, 12, 31))

    assert due is None


def test_unreadable_application_date_gives_no_follow_up():
    no_events: list[TrackingEvent] = []

    due = follow_up_due("pas une date", no_events, SCHEDULE, date(2026, 12, 31))

    assert due is None


def test_each_reached_delay_is_a_new_follow_up_without_noted_one():
    no_events: list[TrackingEvent] = []

    due_on_day_7 = follow_up_due(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 7))
    due_on_day_9 = follow_up_due(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 9))

    assert due_on_day_7 is not None and due_on_day_9 is not None
    assert (due_on_day_7.step, due_on_day_7.due_date) == (1, date(2026, 11, 6))
    assert (due_on_day_9.step, due_on_day_9.due_date) == (2, date(2026, 11, 9))


def test_day_fifteen_after_interview_is_the_third_follow_up_without_noted_one():
    past_interview = [_interview("2026-11-12")]

    due = follow_up_due(APPLIED_AT, past_interview, SCHEDULE, date(2026, 11, 27))

    assert due is not None
    assert (due.step, due.total, due.due_date) == (3, 3, date(2026, 11, 27))

def test_follow_up_noted_on_interview_day_does_not_count_after_interview():
    events = [_interview("2026-11-12"), _relance("2026-11-12")]

    due = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 11, 17))

    assert due is not None
    assert (due.since, due.step, due.due_date) == (SINCE_INTERVIEW, 1, date(2026, 11, 17))


def test_interview_planned_today_is_still_upcoming():
    interview_today = [_interview("2026-11-12")]

    due = follow_up_due(APPLIED_AT, interview_today, SCHEDULE, date(2026, 11, 12))

    assert due is None


def test_unreadable_planned_date_falls_back_to_recording_date():
    bad_date_interview = [
        TrackingEvent(kind="interview", at="2026-11-04T10:00:00+00:00", event_date="12/11/2026")
    ]

    due = follow_up_due(APPLIED_AT, bad_date_interview, SCHEDULE, date(2026, 11, 9))

    assert due is not None
    assert (due.since, due.start_date) == (SINCE_INTERVIEW, date(2026, 11, 4))


def test_application_timestamp_is_read_in_local_time(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "Europe/Paris")
    time.tzset()
    try:
        late_night_applied_at = "2026-11-01T23:30:00+00:00"  # 00h30 le 2 novembre à Paris
        no_events: list[TrackingEvent] = []

        due = follow_up_due(late_night_applied_at, no_events, SCHEDULE, date(2026, 11, 7))

        assert due is not None
        assert due.start_date == date(2026, 11, 2)
    finally:
        monkeypatch.undo()
        time.tzset()


def test_next_follow_up_before_first_delay_is_the_first():
    no_events: list[TrackingEvent] = []

    upcoming = next_follow_up(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 3))

    assert upcoming is not None
    assert (upcoming.step, upcoming.total, upcoming.due_date) == (1, 2, date(2026, 11, 6))


def test_no_next_follow_up_while_one_is_due():
    no_events: list[TrackingEvent] = []

    upcoming = next_follow_up(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 7))

    assert upcoming is None


def test_no_next_follow_up_once_every_delay_is_reached():
    no_events: list[TrackingEvent] = []

    upcoming = next_follow_up(APPLIED_AT, no_events, SCHEDULE, date(2026, 11, 20))

    assert upcoming is None


def test_next_follow_up_after_a_noted_one_is_last_delay_later():
    one_relance = [_relance("2026-11-06")]

    upcoming = next_follow_up(APPLIED_AT, one_relance, SCHEDULE, date(2026, 11, 7))

    assert upcoming is not None
    assert (upcoming.step, upcoming.due_date) == (2, date(2026, 11, 14))


def test_no_next_follow_up_while_an_interview_is_upcoming():
    upcoming_interview = [_interview("2026-11-30")]

    upcoming = next_follow_up(APPLIED_AT, upcoming_interview, SCHEDULE, date(2026, 11, 20))

    assert upcoming is None


def test_follow_up_noted_after_second_delay_settles_the_second():
    relance_on_day_9 = [_relance("2026-11-10")]

    due = follow_up_due(APPLIED_AT, relance_on_day_9, SCHEDULE, date(2026, 12, 31))
    upcoming = next_follow_up(APPLIED_AT, relance_on_day_9, SCHEDULE, date(2026, 11, 10))

    assert due is None
    assert upcoming is None


def test_follow_up_noted_after_fifteen_days_without_earlier_one_settles_the_third():
    events = [_interview("2026-11-12"), _relance("2026-11-28")]

    due = follow_up_due(APPLIED_AT, events, SCHEDULE, date(2026, 12, 31))

    assert due is None


def test_follow_up_noted_between_delays_settles_the_first():
    relance_on_day_6 = [_relance("2026-11-07")]

    upcoming = next_follow_up(APPLIED_AT, relance_on_day_6, SCHEDULE, date(2026, 11, 8))

    assert upcoming is not None
    assert (upcoming.step, upcoming.due_date) == (2, date(2026, 11, 15))
