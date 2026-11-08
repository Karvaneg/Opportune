"""Tests du stockage des délais de relance (OPP-235)."""

import pytest

from app.follow_up import FollowUpSchedule
from app.follow_up_settings_store import FollowUpSettingsStore


def test_missing_file_gives_default_delays(tmp_path):
    store = FollowUpSettingsStore(tmp_path / "follow_up.json")

    schedule = store.load()

    assert schedule == FollowUpSchedule(after_application=(5, 8), after_interview=(5, 8, 15))


def test_saved_delays_are_read_back(tmp_path):
    store = FollowUpSettingsStore(tmp_path / "follow_up.json")

    store.save([3, 7], [4, 10, 20])

    assert store.load() == FollowUpSchedule(after_application=(3, 7), after_interview=(4, 10, 20))


def test_empty_list_disables_follow_ups_for_that_case(tmp_path):
    store = FollowUpSettingsStore(tmp_path / "follow_up.json")

    store.save([], [5])

    assert store.load().after_application == ()


@pytest.mark.parametrize(
    "delays",
    [[8, 5], [5, 5], [0], [366], [5.5], ["5"], [True], "5, 8", list(range(1, 12))],
)
def test_invalid_delays_are_refused_and_nothing_is_written(tmp_path, delays):
    path = tmp_path / "follow_up.json"
    store = FollowUpSettingsStore(path)

    with pytest.raises(ValueError):
        store.save(delays, [5, 8, 15])

    assert not path.exists()


def test_corrupted_file_gives_default_delays(tmp_path):
    path = tmp_path / "follow_up.json"
    path.write_text('{"after_application": [8, 5], "after_interview": "x"}', encoding="utf-8")
    store = FollowUpSettingsStore(path)

    schedule = store.load()

    assert schedule == FollowUpSchedule()


def test_one_invalid_list_keeps_the_other(tmp_path):
    path = tmp_path / "follow_up.json"
    path.write_text('{"after_application": [3, 6], "after_interview": "x"}', encoding="utf-8")
    store = FollowUpSettingsStore(path)

    schedule = store.load()

    assert schedule == FollowUpSchedule(after_application=(3, 6), after_interview=(5, 8, 15))


def test_clear_restores_default_delays(tmp_path):
    store = FollowUpSettingsStore(tmp_path / "follow_up.json")
    store.save([1], [2])

    store.clear()

    assert store.load() == FollowUpSchedule()


def test_save_leaves_no_temporary_file(tmp_path):
    store = FollowUpSettingsStore(tmp_path / "follow_up.json")

    store.save([3, 6], [4])

    assert sorted(p.name for p in tmp_path.iterdir()) == ["follow_up.json"]
