"""Tests de la récupération d'URL et des garde-fous SSRF (OPP-148).

Aucun réseau : le transport et la résolution DNS sont injectés.
"""

import urllib.error
import urllib.request

import pytest

from app.url_fetch import (
    BlockedError,
    EmptyContentError,
    HtmlDocument,
    UnsupportedUrlError,
    UrlUnreachableError,
    _decode_body,
    _SafeRedirectHandler,
    assert_safe_url,
    fetch_html,
)

# Résolveur public factice (aucune IP interne) pour les cas nominaux.
PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731


# --- Garde-fous SSRF ---------------------------------------------------------

@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x/y", "gopher://x", "/relative"])
def test_assert_safe_url_rejects_non_http_scheme(url):
    with pytest.raises(UnsupportedUrlError):
        assert_safe_url(url, resolve=PUBLIC)


def test_assert_safe_url_rejects_localhost_by_name():
    with pytest.raises(UnsupportedUrlError):
        assert_safe_url("http://localhost/offre", resolve=PUBLIC)


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1", "169.254.1.1", "0.0.0.0"],
)
def test_assert_safe_url_rejects_internal_ip_literals(ip):
    # IP littérale interne → refus sans DNS (resolve renvoie l'IP telle quelle par défaut).
    with pytest.raises(UnsupportedUrlError):
        assert_safe_url(f"http://{ip}/offre")


def test_assert_safe_url_rejects_host_resolving_to_internal():
    # Un nom public qui résout vers une IP privée (DNS rebinding) est refusé.
    with pytest.raises(UnsupportedUrlError):
        assert_safe_url("http://evil.example/x", resolve=lambda host: ["10.1.2.3"])


def test_assert_safe_url_allows_public():
    assert_safe_url("https://example.com/offre", resolve=PUBLIC)  # ne lève pas


# --- fetch_html : succès et mapping d'erreurs --------------------------------

def test_fetch_html_returns_document():
    transport = lambda url, timeout: ("<html><body>Offre</body></html>", "text/html")  # noqa: E731
    doc = fetch_html("https://example.com/o", transport=transport, resolve=PUBLIC)
    assert isinstance(doc, HtmlDocument)
    assert "Offre" in doc.html
    assert doc.url == "https://example.com/o"


def test_fetch_html_empty_body_raises():
    transport = lambda url, timeout: ("   ", "text/html")  # noqa: E731
    with pytest.raises(EmptyContentError):
        fetch_html("https://example.com/o", transport=transport, resolve=PUBLIC)


@pytest.mark.parametrize("code", [404, 410, 500])
def test_fetch_html_http_error_unreachable(code):
    def transport(url, timeout):
        raise urllib.error.HTTPError(url, code, "nope", {}, None)

    with pytest.raises(UrlUnreachableError):
        fetch_html("https://example.com/o", transport=transport, resolve=PUBLIC)


@pytest.mark.parametrize("code", [403, 429])
def test_fetch_html_http_error_blocked(code):
    def transport(url, timeout):
        raise urllib.error.HTTPError(url, code, "blocked", {}, None)

    with pytest.raises(BlockedError):
        fetch_html("https://example.com/o", transport=transport, resolve=PUBLIC)


def test_fetch_html_network_error_unreachable():
    def transport(url, timeout):
        raise urllib.error.URLError("dns down")

    with pytest.raises(UrlUnreachableError):
        fetch_html("https://example.com/o", transport=transport, resolve=PUBLIC)


def test_fetch_html_timeout_unreachable():
    def transport(url, timeout):
        raise TimeoutError("too slow")

    with pytest.raises(UrlUnreachableError):
        fetch_html("https://example.com/o", transport=transport, resolve=PUBLIC)


@pytest.mark.parametrize("url", ["", "   ", None])
def test_fetch_html_empty_url_rejected(url):
    with pytest.raises(UnsupportedUrlError):
        fetch_html(url, transport=lambda u, t: ("x", ""), resolve=PUBLIC)


# --- Revalidation SSRF à chaque redirection ----------------------------------

def test_redirect_to_internal_target_is_refused():
    # Une 302 vers une cible interne est revalidée et refusée (pas de contournement SSRF).
    handler = _SafeRedirectHandler(resolve=lambda host: ["10.1.2.3"])
    with pytest.raises(UnsupportedUrlError):
        handler.redirect_request(None, None, 302, "Found", {}, "http://evil.example/internal")


def test_redirect_to_public_target_is_allowed():
    # Une redirection vers une cible publique passe la revalidation (délègue au parent urllib).
    handler = _SafeRedirectHandler(resolve=PUBLIC)
    req = urllib.request.Request("https://example.com/o")
    new = handler.redirect_request(req, None, 302, "Found", {}, "https://example.com/final")
    assert new is not None  # requête de redirection construite, cible publique autorisée


# --- Décodage tolérant au charset --------------------------------------------

def test_decode_body_falls_back_on_unknown_charset():
    # Charset annoncé introuvable (« charset=bidon ») : repli utf-8 au lieu d'un LookupError.
    assert _decode_body("héllo".encode("utf-8"), "bidon") == "héllo"


def test_decode_body_uses_declared_charset():
    assert _decode_body("héllo".encode("latin-1"), "latin-1") == "héllo"
