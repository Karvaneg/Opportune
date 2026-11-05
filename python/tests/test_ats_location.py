"""Tests du filtre France des offres d'ATS (OPP-226, RG-12)."""

import pytest

from app.ats_company import GREENHOUSE, LEVER
from app.ats_location import is_in_france


@pytest.mark.parametrize(
    "posting",
    [
        {"country": "FR", "categories": {"location": "Paris"}},
        {"country": "fr"},
        {"categories": {"location": "Lyon, France"}},
        {"categories": {"location": "Remote", "allLocations": ["Berlin", "Paris, France"]}},
    ],
)
def test_lever_keeps_postings_located_in_france(posting):
    assert is_in_france(LEVER, posting) is True


@pytest.mark.parametrize(
    "posting",
    [
        {"country": "BR", "categories": {"location": "São Paulo, Brazil"}},
        {"categories": {"location": "Remote"}},
        {"categories": "pas un objet"},
        {},
    ],
)
def test_lever_excludes_postings_outside_france_or_without_country(posting):
    assert is_in_france(LEVER, posting) is False


@pytest.mark.parametrize(
    "job",
    [
        {"location": {"name": "Paris, France"}},
        {"location": {"name": "Remote"}, "offices": [{"name": "France"}]},
        {
            "location": {"name": "Hybride"},
            "offices": [{"name": "HQ", "location": "Nantes, FRANCE"}],
        },
        {"location": {"name": "Paris"}, "offices": [{"name": "Paris"}]},
        {"location": {"name": "Remote - Lyon"}},
        {"location": {"name": "Saint-Étienne"}},
        {"location": {"name": "Paris or Berlin, Germany"}},
        {"location": {"name": "London; Lyon"}},
        {"location": {"name": "Angers, Maine-et-Loire"}},
        {"location": {"name": "Paris, Île-de-France"}},
        {"location": {"name": "Paris, Berlin, Germany"}},
        {"location": {"name": "La Défense"}},
        {"location": {"name": "Remote in Paris"}},
    ],
)
def test_greenhouse_keeps_jobs_located_in_france(job):
    assert is_in_france(GREENHOUSE, job) is True


@pytest.mark.parametrize(
    "job",
    [
        {"location": {"name": "Berlin, Berlin, Germany"}},
        {"location": {"name": "Remote"}},
        {"location": {"name": "Venice, Italy"}},
        {"location": {"name": "Toursky"}},
        {"location": {"name": "Paris, Texas"}},
        {"location": {"name": "Brest, Belarus"}},
        {"location": {"name": "Tours, Belgium"}},
        {"location": {"name": "Orléans, Ontario"}},
        {"location": {"name": "Paris, TX"}},
        {"location": {"name": "Nice, CA"}},
        {"location": {"name": "Paris, Texas, United States"}},
        {"location": {"name": "Orléans, ON, Canada"}},
        {"offices": "pas une liste"},
        {},
    ],
)
def test_greenhouse_excludes_jobs_outside_france_or_without_country(job):
    assert is_in_france(GREENHOUSE, job) is False


def test_unknown_ats_is_never_in_france():
    assert is_in_france("workday", {"country": "FR"}) is False
