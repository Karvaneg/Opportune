"""Tests des réglages de collecte pré-remplis de l'espace démo (OPP-226)."""

import pytest

from app.ats_companies_store import AtsCompaniesStore
from app.ats_company import GREENHOUSE, LEVER, AtsCompany
from app.demo_settings import (
    DEMO_RSS_FEEDS,
    SEEDED_MARKER,
    demo_ats_companies,
    ensure_demo_settings_seeded,
    mark_demo_settings_seeded,
    seed_demo_settings,
)
from app.rss_feeds_store import RssFeedsStore


def test_demo_ats_companies_are_swile_on_lever_and_mirakl_on_greenhouse():
    expected_companies = [AtsCompany(LEVER, "swile"), AtsCompany(GREENHOUSE, "mirakl")]

    assert demo_ats_companies() == expected_companies


def test_seed_demo_settings_writes_feeds_and_companies(tmp_path):
    rss_feeds = RssFeedsStore(tmp_path / "rss.json")
    ats_companies = AtsCompaniesStore(tmp_path / "ats.json")

    seed_demo_settings(rss_feeds=rss_feeds, ats_companies=ats_companies)

    assert rss_feeds.load() == list(DEMO_RSS_FEEDS)
    assert ats_companies.load() == demo_ats_companies()


def test_seed_demo_settings_replaces_previous_settings(tmp_path):
    rss_feeds = RssFeedsStore(tmp_path / "rss.json")
    ats_companies = AtsCompaniesStore(tmp_path / "ats.json")
    rss_feeds.save(["https://exemple.fr/offres.rss"])
    ats_companies.save([AtsCompany(LEVER, "autre")])

    seed_demo_settings(rss_feeds=rss_feeds, ats_companies=ats_companies)

    assert rss_feeds.load() == list(DEMO_RSS_FEEDS)
    assert ats_companies.load() == demo_ats_companies()


def _stores(settings_dir):
    return {
        "rss_feeds": RssFeedsStore(settings_dir / "rss.json"),
        "ats_companies": AtsCompaniesStore(settings_dir / "ats.json"),
    }


def test_ensure_seeds_once_then_leaves_user_changes_alone(tmp_path):
    stores = _stores(tmp_path)
    ensure_demo_settings_seeded(tmp_path, **stores)
    stores["ats_companies"].save([AtsCompany(LEVER, "autre")])

    seeded_again = ensure_demo_settings_seeded(tmp_path, **stores)

    assert seeded_again is False
    assert stores["ats_companies"].load() == [AtsCompany(LEVER, "autre")]


def test_ensure_seeds_an_existing_demo_that_was_never_seeded(tmp_path):
    stores = _stores(tmp_path)
    stores["rss_feeds"].save(["https://exemple.fr/offres.rss"])

    seeded = ensure_demo_settings_seeded(tmp_path, **stores)

    assert seeded is True
    assert stores["ats_companies"].load() == demo_ats_companies()


def test_ensure_does_not_reseed_after_a_reset(tmp_path):
    stores = _stores(tmp_path)
    mark_demo_settings_seeded(tmp_path)

    seeded = ensure_demo_settings_seeded(tmp_path, **stores)

    assert seeded is False
    assert stores["ats_companies"].load() == []


class _UnwritableAtsStore(AtsCompaniesStore):
    def save(self, companies):
        raise PermissionError("lecture seule")


def test_failed_write_leaves_no_marker_so_next_start_retries(tmp_path):
    stores = {
        "rss_feeds": RssFeedsStore(tmp_path / "rss.json"),
        "ats_companies": _UnwritableAtsStore(tmp_path / "ats.json"),
    }

    with pytest.raises(OSError):
        ensure_demo_settings_seeded(tmp_path, **stores)

    assert not (tmp_path / SEEDED_MARKER).exists()
