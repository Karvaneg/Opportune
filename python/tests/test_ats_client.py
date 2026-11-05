"""Tests du client des API publiques Greenhouse / Lever (OPP-226), sans réseau."""

import http.client
import json
import ssl

import pytest

from app import http_get
from app.adzuna_client import HttpResponse
from app.ats_client import (
    AtsClient,
    AtsError,
    AtsNotFoundError,
    AtsRateLimitError,
    AtsUnavailableError,
    jobs_url,
)
from app.ats_company import GREENHOUSE, LEVER, AtsCompany


def _client(status: int, body: object, calls: list[str] | None = None) -> AtsClient:
    def transport(url: str) -> HttpResponse:
        if calls is not None:
            calls.append(url)
        return HttpResponse(status, body if isinstance(body, str) else json.dumps(body))

    return AtsClient(transport=transport)


@pytest.mark.parametrize(
    ("company", "expected_url"),
    [
        (
            AtsCompany(GREENHOUSE, "mirakl"),
            "https://boards-api.greenhouse.io/v1/boards/mirakl/jobs?content=true",
        ),
        (AtsCompany(LEVER, "swile"), "https://api.lever.co/v0/postings/swile?mode=json"),
        (
            AtsCompany(LEVER, "acme", eu=True),
            "https://api.eu.lever.co/v0/postings/acme?mode=json",
        ),
    ],
)
def test_jobs_url_targets_public_read_api(company, expected_url):
    assert jobs_url(company) == expected_url


def test_jobs_url_can_skip_greenhouse_descriptions():
    company = AtsCompany(GREENHOUSE, "mirakl")

    light_url = jobs_url(company, with_content=False)

    assert light_url == "https://boards-api.greenhouse.io/v1/boards/mirakl/jobs"


def test_list_jobs_unwraps_greenhouse_envelope():
    client = _client(200, {"jobs": [{"id": 1}, {"id": 2}]})

    greenhouse_jobs = client.list_jobs(AtsCompany(GREENHOUSE, "mirakl"))

    assert greenhouse_jobs == [{"id": 1}, {"id": 2}]


def test_list_jobs_reads_bare_lever_list():
    client = _client(200, [{"id": "a"}, "pas un objet"])

    lever_postings = client.list_jobs(AtsCompany(LEVER, "swile"))

    assert lever_postings == [{"id": "a"}]


def test_list_jobs_makes_a_single_request_per_company():
    calls: list[str] = []
    client = _client(200, [], calls)

    client.list_jobs(AtsCompany(LEVER, "swile"))

    assert calls == ["https://api.lever.co/v0/postings/swile?mode=json"]


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (404, AtsNotFoundError),
        (429, AtsRateLimitError),
        (503, AtsUnavailableError),
        (403, AtsError),
    ],
)
def test_list_jobs_maps_http_statuses_to_typed_errors(status, expected_error):
    client = _client(status, "")

    with pytest.raises(expected_error):
        client.list_jobs(AtsCompany(LEVER, "swile"))


@pytest.mark.parametrize("body", ["{pas du json", {"ok": True}, '"texte"'])
def test_list_jobs_rejects_unreadable_or_unexpected_payload(body):
    client = _client(200, body)

    with pytest.raises(AtsError):
        client.list_jobs(AtsCompany(GREENHOUSE, "mirakl"))


class _BrokenResponse:
    """Réponse ``urlopen`` dont la lecture du corps échoue (connexion coupée en cours de route)."""

    status = 200

    def __init__(self, error: Exception) -> None:
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self):
        raise self._error


@pytest.mark.parametrize(
    "read_error",
    [
        ConnectionResetError("connexion réinitialisée"),
        ssl.SSLError("poignée de main TLS interrompue"),
        http.client.IncompleteRead(b"{\"jobs\": ["),
    ],
)
def test_default_transport_turns_body_read_failures_into_unavailable(monkeypatch, read_error):
    monkeypatch.setattr(
        http_get.urllib.request, "urlopen", lambda *args, **kwargs: _BrokenResponse(read_error)
    )
    client = AtsClient()

    with pytest.raises(AtsUnavailableError):
        client.list_jobs(AtsCompany(GREENHOUSE, "mirakl"))
