"""Tests de la mise à jour des entreprises ciblées (OPP-226, RG-1 à RG-7)."""

import threading
import time

import pytest

from app.ats_client import AtsNotFoundError, AtsUnavailableError
from app.ats_companies_service import (
    MAX_COMPANIES,
    AtsVerificationUnavailable,
    CompanyCheck,
    update_companies,
)
from app.ats_companies_store import AtsCompaniesStore
from app.ats_company import GREENHOUSE, LEVER, AtsCompany


class FakeAtsClient:
    def __init__(self, jobs_by_slug: dict[str, object] | None = None) -> None:
        self._jobs_by_slug = jobs_by_slug or {}
        self.calls: list[str] = []
        self.with_content: list[bool] = []

    def list_jobs(self, company: AtsCompany, *, with_content: bool = True) -> list[dict]:
        self.calls.append(company.slug)
        self.with_content.append(with_content)
        jobs = self._jobs_by_slug.get(company.slug, [])
        if isinstance(jobs, Exception):
            raise jobs
        return jobs


def test_saves_verified_companies_with_their_offers_in_france(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    client = FakeAtsClient({"swile": [{"country": "FR"}, {"country": "BR"}], "mirakl": []})

    checks = update_companies(
        ["https://jobs.lever.co/swile", "job-boards.greenhouse.io/mirakl"],
        store=store,
        client=client,
    )

    assert checks == [
        CompanyCheck(AtsCompany(LEVER, "swile"), offers_in_france=1),
        CompanyCheck(AtsCompany(GREENHOUSE, "mirakl"), offers_in_france=0),
    ]
    assert store.load() == [AtsCompany(LEVER, "swile"), AtsCompany(GREENHOUSE, "mirakl")]


def test_rejects_everything_and_cites_each_invalid_line(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])

    with pytest.raises(ValueError) as error:
        update_companies(
            ["https://jobs.lever.co/qonto", "https://wttj.com/x", "pas une url"],
            store=store,
            client=FakeAtsClient(),
        )

    assert "https://wttj.com/x" in str(error.value)
    assert "pas une url" in str(error.value)
    assert "jobs.lever.co/{entreprise}" in str(error.value)
    assert store.load() == [AtsCompany(LEVER, "swile")]


def test_same_company_pasted_twice_is_kept_once(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")

    checks = update_companies(
        ["https://boards.greenhouse.io/mirakl", "https://job-boards.greenhouse.io/Mirakl/jobs/1"],
        store=store,
        client=FakeAtsClient(),
    )

    assert [check.company for check in checks] == [AtsCompany(GREENHOUSE, "mirakl")]


def test_refuses_more_than_the_maximum(tmp_path):
    too_many_lines = [f"https://jobs.lever.co/c{n}" for n in range(MAX_COMPANIES + 1)]

    with pytest.raises(ValueError, match=f"{MAX_COMPANIES} entreprises maximum"):
        update_companies(
            too_many_lines, store=AtsCompaniesStore(tmp_path / "a.json"), client=FakeAtsClient()
        )


def test_unknown_company_on_its_ats_is_refused(tmp_path):
    client = FakeAtsClient({"ghost": AtsNotFoundError("404")})

    with pytest.raises(ValueError, match="entreprise introuvable sur Lever"):
        update_companies(
            ["jobs.lever.co/ghost"], store=AtsCompaniesStore(tmp_path / "a.json"), client=client
        )


def test_unreachable_ats_blocks_saving(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    client = FakeAtsClient({"swile": AtsUnavailableError("réseau")})

    with pytest.raises(AtsVerificationUnavailable):
        update_companies(["jobs.lever.co/swile"], store=store, client=client)

    assert store.load() == []


def test_already_saved_companies_are_not_verified_again(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])
    client = FakeAtsClient()

    checks = update_companies(
        ["jobs.lever.co/swile", "jobs.lever.co/qonto"], store=store, client=client
    )

    assert client.calls == ["qonto"]
    assert checks[0] == CompanyCheck(AtsCompany(LEVER, "swile"), offers_in_france=None)


@pytest.mark.parametrize("lines", [[], ["", "   "]])
def test_no_input_clears_every_company(tmp_path, lines):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])

    checks = update_companies(lines, store=store, client=FakeAtsClient())

    assert checks == []
    assert store.load() == []


@pytest.mark.parametrize("lines", [[None], ["jobs.lever.co/swile", 42]])
def test_non_text_entries_are_refused_and_nothing_is_cleared(tmp_path, lines):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    store.save([AtsCompany(LEVER, "swile")])

    with pytest.raises(ValueError):
        update_companies(lines, store=store, client=FakeAtsClient())

    assert store.load() == [AtsCompany(LEVER, "swile")]


def test_verification_asks_for_the_light_listing_without_descriptions(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    client = FakeAtsClient()

    update_companies(["job-boards.greenhouse.io/mirakl"], store=store, client=client)

    assert client.with_content == [False]


class ConcurrencyTrackingAtsClient(FakeAtsClient):
    """Retient le nombre maximal d'appels en cours au même moment."""

    def __init__(self, jobs_by_slug: dict[str, object] | None = None) -> None:
        super().__init__(jobs_by_slug)
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def list_jobs(self, company: AtsCompany, *, with_content: bool = True) -> list[dict]:
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            time.sleep(0.01)
            return super().list_jobs(company, with_content=with_content)
        finally:
            with self._lock:
                self._in_flight -= 1


def test_new_companies_are_verified_one_at_a_time_in_input_order(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    client = ConcurrencyTrackingAtsClient()
    lines = ["jobs.lever.co/a", "jobs.lever.co/b", "jobs.lever.co/c"]

    update_companies(lines, store=store, client=client)

    assert client.max_in_flight == 1
    assert client.calls == ["a", "b", "c"]


def test_verification_stops_at_the_first_error(tmp_path):
    store = AtsCompaniesStore(tmp_path / "ats.json")
    client = FakeAtsClient({"ghost": AtsNotFoundError("404")})
    lines = ["jobs.lever.co/a", "jobs.lever.co/ghost", "jobs.lever.co/c"]

    with pytest.raises(ValueError, match="introuvable"):
        update_companies(lines, store=store, client=client)

    assert client.calls == ["a", "ghost"]
    assert store.load() == []
