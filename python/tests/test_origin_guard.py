"""Tests du contrôle de l'en-tête ``Origin`` sur les écritures (OPP-233), sans serveur."""

import pytest

from api.origin_guard import allowed_origins, is_write_allowed, parse_extra_origins


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://[::1]:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
        "http://localhost:4173",
        "HTTP://LOCALHOST:8000",
        "http://localhost:8000/",
    ],
)
def test_app_and_dev_front_origins_are_allowed_in_dev(origin):
    dev_origins = allowed_origins(8000, allow_dev_front=True)

    allowed = is_write_allowed(origin, dev_origins)

    assert allowed is True


@pytest.mark.parametrize(
    "origin", ["http://localhost:5173", "http://127.0.0.1:4173", "http://[::1]:5173"]
)
def test_dev_front_origins_are_refused_in_packaged_app(origin):
    packaged_origins = allowed_origins(8000, allow_dev_front=False)

    allowed = is_write_allowed(origin, packaged_origins)

    assert allowed is False


def test_api_origin_is_allowed_in_packaged_app():
    packaged_origins = allowed_origins(8000, allow_dev_front=False)

    allowed = is_write_allowed("http://127.0.0.1:8000", packaged_origins)

    assert allowed is True


def test_missing_origin_is_allowed():
    dev_origins = allowed_origins(8000, allow_dev_front=True)

    allowed = is_write_allowed(None, dev_origins)

    assert allowed is True


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "http://evil.example:8000",
        "https://localhost:8000",
        "http://localhost:9000",
        "http://localhost",
        "http://127.0.0.1.evil.example:8000",
        "http://172.18.0.5:5173",
        "null",
        "",
    ],
)
def test_foreign_origins_are_refused(origin):
    dev_origins = allowed_origins(8000, allow_dev_front=True)

    allowed = is_write_allowed(origin, dev_origins)

    assert allowed is False


def test_api_origin_follows_listening_port():
    origins_on_8765 = allowed_origins(8765, allow_dev_front=False)

    allowed_on_new_port = is_write_allowed("http://127.0.0.1:8765", origins_on_8765)
    allowed_on_default_port = is_write_allowed("http://127.0.0.1:8000", origins_on_8765)

    assert allowed_on_new_port is True
    assert allowed_on_default_port is False


def test_extra_origins_are_parsed_and_normalized():
    env = {"OPPORTUNE_EXTRA_ORIGINS": " http://172.18.0.5:5173/ , ,HTTP://Mon-PC:5173"}

    extra_origins = parse_extra_origins(env)

    assert extra_origins == ("http://172.18.0.5:5173", "http://mon-pc:5173")


def test_missing_extra_origins_variable_gives_none():
    env: dict[str, str] = {}

    extra_origins = parse_extra_origins(env)

    assert extra_origins == ()


def test_extra_origin_is_allowed():
    origins_with_wsl_front = allowed_origins(
        8000, allow_dev_front=True, extra=("http://172.18.0.5:5173",)
    )

    allowed = is_write_allowed("http://172.18.0.5:5173", origins_with_wsl_front)

    assert allowed is True
