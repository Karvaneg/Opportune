"""Tests du câblage d'authentification du serveur (OPP-099).

Vérifie que la composition ``build_auth`` / ``_ttl_to_expires_at`` produit bien un
``AuthProvider`` avec expiration **réelle** quand un TTL est fourni — sans démarrer de
serveur (helpers isolés du ``main`` réseau). La logique d'expiration elle-même est testée
dans ``test_auth.py`` (OPP-098) ; ici on ne teste que le **câblage**.
"""

from datetime import datetime, timezone

import pytest

from api.server import _ttl_to_expires_at, build_auth, parse_ttl_seconds

_UTC = timezone.utc


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_build_auth_without_expiry_is_valid_anytime():
    # Pas de TTL → jeton sans échéance (User nu), valable même dans un futur lointain.
    auth = build_auth("tok", ["cand-1"], now=lambda: datetime(2999, 1, 1, tzinfo=_UTC))
    user = auth.authenticate(_hdr("tok"))
    assert user is not None
    assert user.owns("cand-1") and user.is_reviewer


def test_ttl_to_expires_at_is_issue_plus_ttl():
    issued = datetime(2026, 9, 4, 12, 0, 0, tzinfo=_UTC)
    assert _ttl_to_expires_at(3600, issued_at=issued) == datetime(
        2026, 9, 4, 13, 0, 0, tzinfo=_UTC
    ).isoformat()


def test_ttl_token_valid_before_expiry_then_expired():
    issued = datetime(2026, 9, 4, 12, 0, 0, tzinfo=_UTC)
    expires_at = _ttl_to_expires_at(3600, issued_at=issued)  # 13:00Z

    valid = build_auth("tok", ["cand-1"], expires_at=expires_at,
                       now=lambda: datetime(2026, 9, 4, 12, 30, tzinfo=_UTC))
    assert valid.authenticate(_hdr("tok")) is not None

    # À l'échéance exacte (frontière exclusive) → expiré.
    expired = build_auth("tok", ["cand-1"], expires_at=expires_at,
                         now=lambda: datetime(2026, 9, 4, 13, 0, tzinfo=_UTC))
    assert expired.authenticate(_hdr("tok")) is None


def test_build_auth_grants_ownership_scope():
    auth = build_auth("tok", ["cand-1", "cand-2"], now=lambda: datetime(2026, 9, 4, tzinfo=_UTC))
    user = auth.authenticate(_hdr("tok"))
    assert user.owns("cand-1") and user.owns("cand-2")
    assert not user.owns("cand-3")


def test_parse_ttl_seconds_absent_or_empty_is_none():
    # Pas de TTL → jeton sans échéance (rétro-compat).
    assert parse_ttl_seconds(None) is None
    assert parse_ttl_seconds("") is None


def test_parse_ttl_seconds_valid_positive():
    assert parse_ttl_seconds("3600") == 3600


@pytest.mark.parametrize("raw", ["abc", "1h", "3.5", "0", "-5"])
def test_parse_ttl_seconds_rejects_invalid(raw):
    # Non entier, nul ou négatif → refus explicite (pas de jeton mort-né ni de int() brut).
    with pytest.raises(ValueError):
        parse_ttl_seconds(raw)
