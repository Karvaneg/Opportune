"""Tests du filtre « poste recherché » des offres d'ATS (OPP-226, RG-11)."""

import pytest

from app.ats_company import GREENHOUSE, LEVER
from app.ats_title_filter import job_title, matches_title


@pytest.mark.parametrize(
    "query, title",
    [
        ("data analyst", "Senior Data Analyst (H/F)"),
        ("Développeur", "developpeur backend"),
        ("developpeur", "Développeur Backend"),
        ("  analyst   data ", "Data Analyst"),
        ("", "Account Executive"),
        ("   ", "Account Executive"),
        ("IA", "Ingénieur IA (H/F)"),
        ("C++", "Développeur C++ embarqué"),
        ("dev", "Développeur Backend"),
        ("product man", "Product Manager"),
    ],
)
def test_matches_title_keeps_titles_containing_every_word(query, title):
    assert matches_title(query, title) is True


@pytest.mark.parametrize(
    "query, title",
    [
        ("data analyst", "Data Engineer"),
        ("développeur", "Software Engineer"),
        ("data", ""),
        ("IA", "Social Media Manager"),
        ("IA", "Commercial"),
        ("veloppeur", "Développeur"),
        ("C++", "Account Executive"),
    ],
)
def test_matches_title_rejects_titles_missing_a_word(query, title):
    assert matches_title(query, title) is False


def test_job_title_reads_greenhouse_title():
    job = {"title": "Data Analyst", "text": "ignoré"}

    assert job_title(GREENHOUSE, job) == "Data Analyst"


def test_job_title_reads_lever_text():
    posting = {"text": "Product Manager", "title": "ignoré"}

    assert job_title(LEVER, posting) == "Product Manager"


def test_job_title_is_empty_when_missing_or_not_a_string():
    posting = {"text": None}

    assert job_title(LEVER, posting) == ""
