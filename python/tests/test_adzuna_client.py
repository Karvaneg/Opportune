"""Tests du client API Adzuna (OPP-120).

Transport injecté : aucun appel réseau, aucun identifiant réel. On vérifie la construction de
la requête (pays, page, identifiants, filtres), la lecture du total (``count``) et la
traduction des statuts HTTP en erreurs typées.
"""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.adzuna_client import (
    AdzunaAuthError,
    AdzunaClient,
    AdzunaCredentials,
    AdzunaError,
    AdzunaQuotaError,
    HttpResponse,
    credentials_from_env,
)


class FakeTransport:
    """Transport scriptable : rejoue des ``HttpResponse`` et enregistre les URLs appelées."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        return self._responses.pop(0)


def _client(responses, **kwargs):
    transport = FakeTransport(responses)
    client = AdzunaClient(
        AdzunaCredentials(app_id="aid", app_key="akey"), transport=transport, **kwargs
    )
    return client, transport


def _page(results, count):
    return HttpResponse(200, json.dumps({"count": count, "results": results}))


# --- credentials_from_env ---------------------------------------------------------------


def test_credentials_from_env_reads_both_values():
    creds = credentials_from_env({"ADZUNA_APP_ID": "abc", "ADZUNA_APP_KEY": "xyz"})
    assert creds == AdzunaCredentials(app_id="abc", app_key="xyz")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"ADZUNA_APP_ID": "abc"},
        {"ADZUNA_APP_KEY": "xyz"},
        {"ADZUNA_APP_ID": " ", "ADZUNA_APP_KEY": "xyz"},
    ],
)
def test_credentials_from_env_raises_when_incomplete(env):
    with pytest.raises(AdzunaAuthError):
        credentials_from_env(env)


# --- search -----------------------------------------------------------------------------


def test_search_builds_country_page_and_credentials():
    client, transport = _client([_page([{"id": "1"}], count=1)], country="fr")

    client.search(page=1, results_per_page=50)

    url = transport.urls[0]
    assert "/jobs/fr/search/1?" in url
    params = parse_qs(urlsplit(url).query)
    assert params["app_id"] == ["aid"]
    assert params["app_key"] == ["akey"]
    assert params["results_per_page"] == ["50"]


def test_search_merges_extra_params():
    client, transport = _client([_page([], count=0)])

    client.search(page=1, results_per_page=50, extra_params={"what": "python", "permanent": "1"})

    params = parse_qs(urlsplit(transport.urls[0]).query)
    assert params["what"] == ["python"]
    assert params["permanent"] == ["1"]


def test_search_returns_offers_and_total_from_count():
    client, _ = _client([_page([{"id": "a"}, {"id": "b"}], count=137)])

    page = client.search(page=1, results_per_page=50)

    assert [o["id"] for o in page.offers] == ["a", "b"]
    assert page.total == 137


def test_search_reads_total_when_count_is_float():
    # Régression : Adzuna renvoie parfois ``count`` en flottant. On doit l'accepter (sinon
    # repli sur la taille de page → arrêt prématuré de la pagination dès la première page).
    client, _ = _client([HttpResponse(200, json.dumps({"count": 137.0, "results": [{"id": "a"}]}))])

    page = client.search(page=1, results_per_page=50)

    assert page.total == 137


def test_search_falls_back_to_seen_count_when_count_absent():
    client, _ = _client([HttpResponse(200, json.dumps({"results": [{"id": "a"}]}))])

    page = client.search(page=1, results_per_page=50)

    assert page.total == 1


def test_search_raises_quota_on_429():
    client, _ = _client([HttpResponse(429, "")])
    with pytest.raises(AdzunaQuotaError):
        client.search(page=1, results_per_page=50)


@pytest.mark.parametrize("status", [401, 403])
def test_search_raises_auth_on_401_403(status):
    client, _ = _client([HttpResponse(status, "")])
    with pytest.raises(AdzunaAuthError):
        client.search(page=1, results_per_page=50)


def test_search_raises_on_unexpected_status():
    client, _ = _client([HttpResponse(500, "boom")])
    with pytest.raises(AdzunaError):
        client.search(page=1, results_per_page=50)


def test_search_raises_on_malformed_json():
    client, _ = _client([HttpResponse(200, "pas du json")])
    with pytest.raises(AdzunaError):
        client.search(page=1, results_per_page=50)
