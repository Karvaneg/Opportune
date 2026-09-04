"""Tests de l'authentification par jeton : validité, expiration, formats (OPP-097/098).

Unitaires sur ``AuthProvider`` (aucun réseau, horloge injectée pour un déterminisme total),
plus un test d'intégration ``dispatch`` vérifiant qu'un jeton expiré donne bien un 401 —
l'authentification tranchant **avant** tout accès à l'orchestrateur.
"""

from datetime import datetime, timezone

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, AuthProvider, TokenRecord, User

_UTC = timezone.utc
_NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=_UTC)


def _user(candidates=("cand-1",)) -> User:
    return User("u", REVIEWER, frozenset(candidates))


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _provider(value, *, now: datetime = _NOW) -> AuthProvider:
    return AuthProvider({"tok": value}, now=lambda: now)


# --- Sans échéance : rétro-compat -------------------------------------------

def test_bare_user_never_expires():
    # ``AuthProvider({token: User})`` reste valide : un User nu = pas d'expiration.
    provider = _provider(_user(), now=datetime(2999, 1, 1, tzinfo=_UTC))
    assert provider.authenticate(_hdr("tok")) == _user()


def test_token_record_without_expiry_never_expires():
    provider = _provider(TokenRecord(_user(), None), now=datetime(2999, 1, 1, tzinfo=_UTC))
    assert provider.authenticate(_hdr("tok")) is not None


# --- Échéance exclusive ------------------------------------------------------

def test_valid_before_expiry():
    provider = _provider(TokenRecord(_user(), "2026-09-04T13:00:00+00:00"))
    assert provider.authenticate(_hdr("tok")) == _user()


def test_expired_after_expiry():
    provider = _provider(TokenRecord(_user(), "2026-09-04T11:00:00+00:00"))
    assert provider.authenticate(_hdr("tok")) is None


def test_exact_boundary_is_expired():
    # Échéance exclusive : à now == expires_at, le jeton est expiré (now == _NOW).
    provider = _provider(TokenRecord(_user(), "2026-09-04T12:00:00+00:00"))
    assert provider.authenticate(_hdr("tok")) is None


# --- Normalisation UTC (pas de comparaison lexicographique naïve) ------------

def test_utc_normalization_makes_offset_expired():
    # 13:00+02:00 == 11:00Z, antérieur à now=12:00Z → expiré malgré "13" > "12" en texte.
    provider = _provider(TokenRecord(_user(), "2026-09-04T13:00:00+02:00"))
    assert provider.authenticate(_hdr("tok")) is None


def test_utc_normalization_keeps_valid():
    provider = _provider(TokenRecord(_user(), "2026-09-04T13:00:00+00:00"))
    assert provider.authenticate(_hdr("tok")) is not None


def test_z_suffix_supported():
    # Le suffixe ``Z`` de l'échéance est accepté (parsing ISO, pré-3.11 inclus).
    provider = _provider(TokenRecord(_user(), "2026-09-04T13:00:00Z"))
    assert provider.authenticate(_hdr("tok")) is not None


def test_naive_expiry_assumed_utc():
    # Échéance naïve (sans fuseau) présumée UTC : 13:00 > 12:00 now → valide.
    provider = _provider(TokenRecord(_user(), "2026-09-04T13:00:00"))
    assert provider.authenticate(_hdr("tok")) is not None


def test_naive_clock_assumed_utc():
    # Horloge naïve présumée UTC : now=13:00 >= expires=13:00 → expiré (frontière exclusive).
    provider = _provider(
        TokenRecord(_user(), "2026-09-04T13:00:00+00:00"),
        now=datetime(2026, 9, 4, 13, 0, 0),  # naïf, sans tzinfo
    )
    assert provider.authenticate(_hdr("tok")) is None


# --- Formats invalides → jeton invalide (jamais valide par défaut) -----------

@pytest.mark.parametrize("expires_at", ["pas-une-date", "", "2026-13-99T00:00:00+00:00"])
def test_invalid_expiry_format_is_rejected(expires_at):
    provider = _provider(TokenRecord(_user(), expires_at))
    assert provider.authenticate(_hdr("tok")) is None


# --- Expiré et inconnu sont indistinguables ----------------------------------

def test_expired_and_unknown_are_both_none():
    provider = _provider(TokenRecord(_user(), "2020-01-01T00:00:00+00:00"))
    assert provider.authenticate(_hdr("tok")) is None       # expiré
    assert provider.authenticate(_hdr("inconnu")) is None   # inconnu


# --- Intégration dispatch : jeton expiré → 401 -------------------------------

def test_expired_token_yields_401_via_dispatch():
    # L'auth tranche avant le routage : orchestrator=None n'est jamais atteint.
    provider = _provider(TokenRecord(_user(), "2020-01-01T00:00:00+00:00"))
    api = HermesApi(orchestrator=None, auth=provider)
    resp = api.dispatch("GET", "/runs/whatever", None, _hdr("tok"))
    assert resp.status == 401
