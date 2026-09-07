"""Tests du transport Discord (OPP-117).

Aucun appel réseau : seul le builder pur et le ``MockDiscordTransport`` sont exercés,
plus la garde « token absent » de l'implémentation HTTP.
"""

import pytest

from app.discord_transport import (
    DiscordError,
    DiscordTransport,
    HttpDiscordTransport,
    MockDiscordTransport,
    build_send_request,
)


# --- build_send_request (pur) ------------------------------------------------


def test_build_send_request_targets_channel_with_bot_auth():
    url, data, headers = build_send_request(
        "123", {"content": "salut"}, token="secret", base="https://api.test/v10"
    )
    assert url == "https://api.test/v10/channels/123/messages"
    assert headers["Authorization"] == "Bot secret"
    assert headers["Content-Type"] == "application/json"
    assert b"salut" in data


def test_build_send_request_rejects_empty_channel_or_token():
    with pytest.raises(ValueError):
        build_send_request("", {}, token="secret")
    with pytest.raises(ValueError):
        build_send_request("123", {}, token="")


# --- MockDiscordTransport ----------------------------------------------------


def test_mock_records_and_returns_message_id():
    transport = MockDiscordTransport(message_id="msg-42")
    result = transport.send_message("chan-1", {"content": "coucou"})

    assert result["id"] == "msg-42"
    assert transport.sent == [{"channel_id": "chan-1", "message": {"content": "coucou"}}]


def test_mock_can_raise():
    transport = MockDiscordTransport(error=DiscordError("boum"))
    with pytest.raises(DiscordError):
        transport.send_message("chan-1", {})


def test_mock_satisfies_transport_contract():
    assert isinstance(MockDiscordTransport(), DiscordTransport)


# --- HttpDiscordTransport (sans réseau) --------------------------------------


def test_http_transport_without_token_raises(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    # token vide explicite (honoré, pas de repli sur l'env) ET aucun argument ni env.
    for transport in (HttpDiscordTransport(token=""), HttpDiscordTransport()):
        with pytest.raises(DiscordError):
            transport.send_message("chan-1", {"content": "x"})
