"""Tests de la source « entreprises ciblées » via ATS (OPP-226, RG-12/15/20)."""

import pytest

from app.ats_client import AtsError, AtsNotFoundError
from app.ats_company import GREENHOUSE, LEVER, AtsCompany
from app.ats_source import AtsSource

SWILE = AtsCompany(LEVER, "swile")
MIRAKL = AtsCompany(GREENHOUSE, "mirakl")
GHOST = AtsCompany(LEVER, "ghost")


class FakeAtsClient:
    """Client factice : offres par identifiant, ou erreur à lever ; mémorise les appels."""

    def __init__(self, jobs_by_slug: dict[str, object]) -> None:
        self._jobs_by_slug = jobs_by_slug
        self.calls: list[str] = []

    def list_jobs(self, company: AtsCompany, *, with_content: bool = True) -> list[dict]:
        self.calls.append(company.slug)
        jobs = self._jobs_by_slug[company.slug]
        if isinstance(jobs, Exception):
            raise jobs
        return jobs


def _lever(n: int, country: str = "FR") -> dict:
    return {
        "text": f"Poste {n}",
        "country": country,
        "hostedUrl": f"https://jobs.lever.co/swile/{n}",
    }


def _greenhouse(n: int, place: str = "Paris, France") -> dict:
    return {"title": f"Job {n}", "location": {"name": place}, "absolute_url": f"https://gh/{n}"}


def test_fetch_emits_only_offers_in_france_and_counts_the_others():
    client = FakeAtsClient({"swile": [_lever(1), _lever(2, "BR")], "mirakl": [_greenhouse(3)]})
    source = AtsSource([SWILE, MIRAKL], client=client)

    emitted_urls = [offer.url for offer in source.fetch()]

    assert emitted_urls == ["https://jobs.lever.co/swile/1", "https://gh/3"]
    assert source.excluded == 1


def test_fetch_skips_offers_whose_title_misses_the_job_title_and_counts_them():
    jobs = [
        {"title": "Senior Data Analyst (H/F)", "location": {"name": "Paris, France"}, "absolute_url": "https://gh/1"},
        {"title": "Account Executive", "location": {"name": "Paris, France"}, "absolute_url": "https://gh/2"},
        {"title": "Data Analyst", "location": {"name": "London, UK"}, "absolute_url": "https://gh/3"},
    ]
    source = AtsSource([MIRAKL], client=FakeAtsClient({"mirakl": jobs}), title_query="data analyst")

    emitted_urls = [offer.url for offer in source.fetch()]

    assert emitted_urls == ["https://gh/1"]
    assert source.off_target == 1
    assert source.excluded == 1


def test_offers_skipped_by_title_do_not_count_towards_max_offers():
    jobs = [_greenhouse(1) | {"title": "Sales"}, _greenhouse(2) | {"title": "Data Engineer"}]
    source = AtsSource(
        [MIRAKL], client=FakeAtsClient({"mirakl": jobs}), max_offers=1, title_query="data"
    )

    emitted_urls = [offer.url for offer in source.fetch()]

    assert emitted_urls == ["https://gh/2"]


def test_fetch_stops_at_max_offers_across_companies():
    client = FakeAtsClient({"swile": [_lever(1), _lever(2)], "mirakl": [_greenhouse(3)]})
    source = AtsSource([SWILE, MIRAKL], client=client, max_offers=2)

    emitted_offers = list(source.fetch())

    assert len(emitted_offers) == 2
    assert client.calls == ["swile"]


def test_failing_company_is_reported_and_the_pass_continues():
    client = FakeAtsClient(
        {
            "ghost": AtsNotFoundError("entreprise introuvable sur Lever : ghost"),
            "mirakl": [_greenhouse(1)],
        }
    )
    source = AtsSource([GHOST, MIRAKL], client=client)

    emitted_offers = list(source.fetch())

    assert [offer.url for offer in emitted_offers] == ["https://gh/1"]
    assert source.warnings == ["entreprise introuvable sur Lever : ghost"]


def test_fetch_raises_when_every_company_failed():
    client = FakeAtsClient({"ghost": AtsError("réponse illisible"), "swile": AtsError("HTTP 403")})
    source = AtsSource([GHOST, SWILE], client=client)

    with pytest.raises(AtsError, match="aucune entreprise ciblée n'a pu être interrogée"):
        list(source.fetch())


def test_fetch_queries_companies_sequentially_in_list_order():
    client = FakeAtsClient({"mirakl": [], "swile": []})
    source = AtsSource([MIRAKL, SWILE], client=client)

    list(source.fetch())

    assert client.calls == ["mirakl", "swile"]

