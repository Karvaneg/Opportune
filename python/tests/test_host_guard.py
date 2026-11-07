"""Tests du contrôle de l'en-tête ``Host`` (OPP-233, anti DNS rebinding), sans serveur."""

import pytest

from api.host_guard import allowed_hosts, is_host_allowed


@pytest.mark.parametrize(
    "host", ["127.0.0.1:8000", "localhost:8000", "[::1]:8000", "LOCALHOST:8000"]
)
def test_loopback_hosts_on_api_port_are_allowed(host):
    hosts_on_8000 = allowed_hosts(8000)

    allowed = is_host_allowed(host, hosts_on_8000)

    assert allowed is True


def test_missing_host_is_allowed():
    hosts_on_8000 = allowed_hosts(8000)

    allowed = is_host_allowed(None, hosts_on_8000)

    assert allowed is True


@pytest.mark.parametrize(
    "host", ["evil.example:8000", "localhost:5173", "localhost", "127.0.0.1:9000", ""]
)
def test_other_hosts_are_refused(host):
    hosts_on_8000 = allowed_hosts(8000)

    allowed = is_host_allowed(host, hosts_on_8000)

    assert allowed is False
