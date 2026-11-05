"""Tests de la conversion d'une offre d'ATS en ``RawOffer`` (OPP-226, RG-16 à RG-18)."""

from app.ats_company import GREENHOUSE, LEVER, AtsCompany
from app.ats_offer import to_raw_offer
from app.offer_source import RawOffer


def test_greenhouse_job_becomes_raw_offer_with_full_unescaped_description():
    company = AtsCompany(GREENHOUSE, "mirakl")
    greenhouse_job = {
        "title": "Backend Engineer",
        "company_name": "Mirakl",
        "location": {"name": "Paris, France"},
        "departments": [{"name": "Engineering"}],
        "content": (
            "&lt;p&gt;Tu construis l&amp;#39;API.&lt;/p&gt;"
            "&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
        ),
        "absolute_url": "https://job-boards.greenhouse.io/mirakl/jobs/1",
    }

    raw_offer = to_raw_offer(company, greenhouse_job)

    assert raw_offer == RawOffer(
        source="greenhouse",
        raw_text=(
            "Backend Engineer — Mirakl\nLieu : Paris, France\n\n"
            "Équipe : Engineering\n\nTu construis l'API.\n- Python"
        ),
        url="https://job-boards.greenhouse.io/mirakl/jobs/1",
    )


def test_greenhouse_job_without_company_name_falls_back_to_slug():
    company = AtsCompany(GREENHOUSE, "mirakl")
    greenhouse_job = {"title": "Data Analyst", "absolute_url": "https://x/1"}

    raw_offer = to_raw_offer(company, greenhouse_job)

    assert raw_offer.raw_text == "Data Analyst — mirakl"


def test_lever_posting_becomes_raw_offer_with_lists_and_slug_as_company():
    company = AtsCompany(LEVER, "swile")
    lever_posting = {
        "text": "Product Designer",
        "categories": {"location": "Paris", "commitment": "Permanent", "team": "Design"},
        "descriptionPlain": "Rejoins l'équipe.",
        "lists": [{"text": "Profil", "content": "<li>Figma</li><li>Curiosité</li>"}],
        "additionalPlain": "Télétravail partiel.",
        "hostedUrl": "https://jobs.lever.co/swile/abc",
    }

    raw_offer = to_raw_offer(company, lever_posting)

    assert raw_offer == RawOffer(
        source="lever",
        raw_text=(
            "Product Designer — swile\nLieu : Paris\nType de contrat : Permanent\n\n"
            "Équipe : Design\n\nRejoins l'équipe.\n\nProfil\n- Figma\n- Curiosité\n\n"
            "Télétravail partiel."
        ),
        url="https://jobs.lever.co/swile/abc",
    )


def test_lever_posting_tolerates_missing_or_malformed_fields():
    company = AtsCompany(LEVER, "swile")
    malformed_posting = {"text": "Stage", "categories": "x", "lists": "y"}

    raw_offer = to_raw_offer(company, malformed_posting)

    assert raw_offer == RawOffer(source="lever", raw_text="Stage — swile", url="")
