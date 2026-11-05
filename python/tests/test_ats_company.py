"""Tests de la lecture des URLs de pages carrière d'ATS (OPP-226, RG-1/RG-2/RG-5)."""

import pytest

from app.ats_company import GREENHOUSE, LEVER, AtsCompany, AtsUrlError, parse_career_url


@pytest.mark.parametrize(
    ("url", "expected_company"),
    [
        ("https://jobs.lever.co/swile", AtsCompany(LEVER, "swile", eu=False)),
        ("https://jobs.eu.lever.co/acme", AtsCompany(LEVER, "acme", eu=True)),
        ("https://boards.greenhouse.io/mirakl", AtsCompany(GREENHOUSE, "mirakl")),
        ("https://job-boards.greenhouse.io/mirakl", AtsCompany(GREENHOUSE, "mirakl")),
        ("https://job-boards.eu.greenhouse.io/raisin", AtsCompany(GREENHOUSE, "raisin", eu=True)),
        ("https://boards.eu.greenhouse.io/raisin", AtsCompany(GREENHOUSE, "raisin", eu=True)),
        (
            "https://boards.greenhouse.io/embed/job_board?for=acme&b=https://acme.fr",
            AtsCompany(GREENHOUSE, "acme"),
        ),
    ],
)
def test_parse_recognizes_supported_hosts(url, expected_company):
    parsed_company = parse_career_url(url)

    assert parsed_company == expected_company


@pytest.mark.parametrize(
    "url",
    [
        "  jobs.lever.co/swile  ",
        "http://jobs.lever.co/swile",
        "https://jobs.lever.co/swile/",
        "https://jobs.lever.co/swile/0d1e-offre?lever-source=x#apply",
        "https://WWW.jobs.lever.co/swile",
    ],
)
def test_parse_ignores_scheme_path_tail_query_and_case_of_host(url):
    parsed_company = parse_career_url(url)

    assert parsed_company == AtsCompany(LEVER, "swile")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://www.welcometothejungle.com/fr/companies/x/jobs",
        "https://jobs.lever.co/",
        "ftp://jobs.lever.co/swile",
        "https://boards.greenhouse.io/embed/job_board",
        "pas une url",
    ],
)
def test_parse_rejects_unknown_or_incomplete_urls(url):
    with pytest.raises(AtsUrlError):
        parse_career_url(url)


def test_key_ignores_slug_case():
    lowercase_company = AtsCompany(GREENHOUSE, "mirakl")
    capitalized_company = AtsCompany(GREENHOUSE, "Mirakl")

    assert lowercase_company.key == capitalized_company.key


def test_key_ignores_eu_hosting_for_greenhouse_only():
    greenhouse_eu_company = AtsCompany(GREENHOUSE, "raisin", eu=True)
    lever_eu_company = AtsCompany(LEVER, "acme", eu=True)

    assert greenhouse_eu_company.key == AtsCompany(GREENHOUSE, "raisin").key
    assert lever_eu_company.key != AtsCompany(LEVER, "acme").key


@pytest.mark.parametrize(
    ("company", "expected_url"),
    [
        (AtsCompany(LEVER, "swile"), "https://jobs.lever.co/swile"),
        (AtsCompany(LEVER, "acme", eu=True), "https://jobs.eu.lever.co/acme"),
        (AtsCompany(GREENHOUSE, "mirakl"), "https://job-boards.greenhouse.io/mirakl"),
        (AtsCompany(GREENHOUSE, "raisin", eu=True), "https://job-boards.eu.greenhouse.io/raisin"),
    ],
)
def test_career_url_is_canonical(company, expected_url):
    assert company.career_url == expected_url
