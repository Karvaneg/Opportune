"""Tests du client API France Travail (OPP-120).

Transport injecté : aucun appel réseau, aucun identifiant réel. On vérifie le flux OAuth2,
la construction des requêtes de recherche, la lecture du total via ``Content-Range`` et la
traduction des statuts HTTP en erreurs typées.
"""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.france_travail_client import (
    FranceTravailAuthError,
    FranceTravailClient,
    FranceTravailCredentials,
    FranceTravailError,
    FranceTravailQuotaError,
    HttpResponse,
    credentials_from_env,
)


class FakeTransport:
    """Transport scriptable : rejoue des ``HttpResponse`` et enregistre les appels reçus."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body})
        return self._responses.pop(0)


def _creds():
    return FranceTravailCredentials(client_id="cid", client_secret="secret")


def _client(responses):
    transport = FakeTransport(responses)
    return FranceTravailClient(_creds(), transport=transport), transport


# --- credentials_from_env ---------------------------------------------------------------


def test_credentials_from_env_reads_both_values():
    creds = credentials_from_env(
        {"FRANCE_TRAVAIL_CLIENT_ID": "abc", "FRANCE_TRAVAIL_CLIENT_SECRET": "xyz"}
    )
    assert creds == FranceTravailCredentials(client_id="abc", client_secret="xyz")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"FRANCE_TRAVAIL_CLIENT_ID": "abc"},
        {"FRANCE_TRAVAIL_CLIENT_SECRET": "xyz"},
        {"FRANCE_TRAVAIL_CLIENT_ID": "  ", "FRANCE_TRAVAIL_CLIENT_SECRET": "xyz"},
    ],
)
def test_credentials_from_env_raises_when_incomplete(env):
    with pytest.raises(FranceTravailAuthError):
        credentials_from_env(env)


# --- fetch_token ------------------------------------------------------------------------


def test_fetch_token_posts_client_credentials_and_returns_access_token():
    client, transport = _client([HttpResponse(200, {}, json.dumps({"access_token": "tok-42"}))])

    token = client.fetch_token()

    assert token == "tok-42"
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    body = parse_qs(call["body"])
    assert body["grant_type"] == ["client_credentials"]
    assert body["client_id"] == ["cid"]
    assert body["client_secret"] == ["secret"]
    assert body["scope"] == ["api_offresdemploiv2 o2dsoffre"]


def test_fetch_token_raises_quota_on_429():
    client, _ = _client([HttpResponse(429, {}, "")])
    with pytest.raises(FranceTravailQuotaError):
        client.fetch_token()


def test_fetch_token_raises_auth_on_non_200():
    client, _ = _client([HttpResponse(400, {}, "invalid_client")])
    with pytest.raises(FranceTravailAuthError):
        client.fetch_token()


def test_fetch_token_raises_auth_when_token_absent():
    client, _ = _client([HttpResponse(200, {}, json.dumps({"token_type": "Bearer"}))])
    with pytest.raises(FranceTravailAuthError):
        client.fetch_token()


# --- search -----------------------------------------------------------------------------


def _page(resultats, total):
    body = json.dumps({"resultats": resultats})
    headers = {"Content-Range": f"offres 0-{len(resultats) - 1}/{total}"}
    return HttpResponse(200, headers, body)


def test_search_builds_request_with_contract_range_and_bearer():
    client, transport = _client([_page([{"id": "1"}], total=1)])

    client.search(token="tok", start=0, end=149)

    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["headers"]["Authorization"] == "Bearer tok"
    params = parse_qs(urlsplit(call["url"]).query)
    assert params["typeContrat"] == ["CDI"]
    assert params["range"] == ["0-149"]


def test_search_merges_extra_params():
    client, transport = _client([_page([], total=0)])

    client.search(token="tok", start=0, end=149, extra_params={"motsCles": "python", "commune": "75056"})

    params = parse_qs(urlsplit(transport.calls[0]["url"]).query)
    assert params["motsCles"] == ["python"]
    assert params["commune"] == ["75056"]


def test_search_returns_offers_and_total_from_content_range():
    client, _ = _client([_page([{"id": "a"}, {"id": "b"}], total=1234)])

    page = client.search(token="tok", start=0, end=149)

    assert [o["id"] for o in page.offers] == ["a", "b"]
    assert page.total == 1234


def test_search_reads_total_from_lowercase_content_range():
    # Régression : un serveur (HTTP/2, proxy…) peut renvoyer l'en-tête en minuscules. La
    # lecture du total doit rester insensible à la casse, sinon la pagination se tronque.
    body = json.dumps({"resultats": [{"id": "a"}, {"id": "b"}]})
    client, _ = _client([HttpResponse(200, {"content-range": "offres 0-1/1234"}, body)])

    page = client.search(token="tok", start=0, end=149)

    assert page.total == 1234


def test_search_treats_206_as_success():
    body = json.dumps({"resultats": [{"id": "x"}]})
    client, _ = _client([HttpResponse(206, {"Content-Range": "offres 0-0/9000"}, body)])

    page = client.search(token="tok", start=0, end=149)

    assert len(page.offers) == 1
    assert page.total == 9000


def test_search_204_is_empty_page():
    client, _ = _client([HttpResponse(204, {}, "")])

    page = client.search(token="tok", start=150, end=299)

    assert page.offers == ()
    assert page.total == 0


def test_search_falls_back_to_seen_count_when_content_range_absent():
    body = json.dumps({"resultats": [{"id": "a"}, {"id": "b"}]})
    client, _ = _client([HttpResponse(200, {}, body)])

    page = client.search(token="tok", start=300, end=449)

    # Sans en-tête Content-Range : total = position de départ + ce qu'on a vu.
    assert page.total == 302


def test_search_raises_quota_on_429():
    client, _ = _client([HttpResponse(429, {}, "")])
    with pytest.raises(FranceTravailQuotaError):
        client.search(token="tok", start=0, end=149)


def test_search_raises_on_unexpected_status():
    client, _ = _client([HttpResponse(500, {}, "boom")])
    with pytest.raises(FranceTravailError):
        client.search(token="tok", start=0, end=149)
