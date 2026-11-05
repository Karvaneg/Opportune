"""Tests du stockage local des entreprises ciblées (OPP-226)."""

import json

from app.ats_companies_store import AtsCompaniesStore, default_ats_companies_path
from app.ats_company import GREENHOUSE, LEVER, AtsCompany


def test_save_then_load_round_trips_companies_in_order(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    companies = [
        AtsCompany(LEVER, "swile"),
        AtsCompany(LEVER, "acme", eu=True),
        AtsCompany(GREENHOUSE, "mirakl"),
    ]

    store.save(companies)

    assert store.load() == companies


def test_load_returns_empty_when_file_absent_or_corrupt(tmp_path):
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{ pas du json", encoding="utf-8")

    absent_companies = AtsCompaniesStore(tmp_path / "absent.json").load()
    corrupt_companies = AtsCompaniesStore(corrupt_path).load()

    assert absent_companies == []
    assert corrupt_companies == []


def test_load_ignores_malformed_entries(tmp_path):
    path = tmp_path / "ats.json"
    path.write_text(
        json.dumps(
            {
                "companies": [
                    {"ats": "lever", "slug": "swile"},
                    {"ats": "workday", "slug": "x"},
                    {"ats": "greenhouse", "slug": "  "},
                    "pas un objet",
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded_companies = AtsCompaniesStore(path).load()

    assert loaded_companies == [AtsCompany(LEVER, "swile")]


def test_clear_removes_the_file_and_is_idempotent(tmp_path):
    path = tmp_path / "ats.json"
    store = AtsCompaniesStore(path)
    store.save([AtsCompany(LEVER, "swile")])

    store.clear()
    store.clear()

    assert not path.exists()
    assert store.load() == []


def test_default_path_honours_data_dir(tmp_path):
    path = default_ats_companies_path(tmp_path)

    assert path == tmp_path / "ats_companies.json"
