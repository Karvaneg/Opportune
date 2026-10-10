"""Récupération du HTML d'une offre depuis son URL (V2, OPP-148).

Chaînon « collecte réelle » : fetch HTTP(S) d'une URL d'offre, pour alimenter ensuite
l'extraction de texte (``html_extract``) puis l'intake texte (OPP-145). Fidèle à la stack
(cf. ``llm_client``), le **transport est injectable** — par défaut ``urllib`` (zéro
dépendance réseau en test) — et les échecs sont convertis en **erreurs typées**.

Garde-fous **SSRF** : le back émet une requête sortante vers une URL **fournie par
l'utilisateur**. On refuse donc tout ce qui n'est pas http(s) et toute cible interne
(localhost, boucle locale, IP privées/lien-local/réservées) — résolution DNS incluse, via
un ``resolve`` lui aussi injectable (tests hermétiques, sans réseau). La validation est
**rejouée à chaque redirection** : une page publique ne peut pas rediriger (302…) vers une
cible interne (169.254.169.254, 127.0.0.1…) pour contourner le filtre.

Résidu connu (hors périmètre) : entre la validation et la connexion, ``urllib`` re-résout le
nom indépendamment — un DNS rebinding (IP publique à la validation, interne à la connexion)
reste théoriquement possible. Le fermer exigerait d'épingler la socket sur l'IP validée
(connexion custom) ; non retenu ici (fetch HTTP simple).
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

# Délai par défaut d'un fetch (secondes) : court, un site qui traîne n'est pas bloquant.
DEFAULT_FETCH_TIMEOUT = 20
# Plafond de lecture : on ne télécharge pas un fichier géant déguisé en page.
_MAX_BYTES = 2_000_000
# User-Agent de navigateur : certains sites renvoient 403 à un UA vide/robot évident. Ce
# n'est pas un contournement d'anti-bot sérieux (JS, challenges) — juste la politesse minimale.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0 Safari/537.36 Opportune/1.0"
)

# Transport : (url, timeout) -> (corps, content_type). Peut lever HTTPError / URLError /
# TimeoutError (comme urllib) ; ``fetch_html`` les convertit en erreurs typées.
Transport = Callable[[str, int], "tuple[str, str]"]
# Résolution DNS : hostname -> liste d'IP (chaînes). Injectable pour des tests hermétiques.
Resolver = Callable[[str], "list[str]"]


class UrlFetchError(Exception):
    """Échec de récupération d'une URL (erreur de base du contrat)."""


class UnsupportedUrlError(UrlFetchError):
    """URL refusée **avant** tout appel réseau : schéma non http(s), ou cible interne (SSRF)."""


class UrlUnreachableError(UrlFetchError):
    """L'URL n'a pu être atteinte : 404/410, DNS, timeout ou autre échec réseau."""


class BlockedError(UrlFetchError):
    """La cible a refusé la requête (403/429) : blocage type anti-bot."""


class EmptyContentError(UrlFetchError):
    """La réponse est vide : rien à extraire."""


@dataclass(frozen=True)
class HtmlDocument:
    """HTML récupéré pour une URL, prêt pour l'extraction de texte."""

    url: str
    html: str
    content_type: str = ""


def _default_resolve(host: str) -> list[str]:
    """Résout ``host`` en IP. Un littéral IP est renvoyé tel quel (pas de DNS)."""
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        infos = socket.getaddrinfo(host, None)
        return [info[4][0] for info in infos]


def _is_blocked_ip(ip: str) -> bool:
    """Une IP interne/non routable publiquement (refus SSRF) ?"""
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_safe_url(url: str, *, resolve: Resolver | None = None) -> None:
    """Valide l'URL **avant** tout appel réseau ; lève ``UnsupportedUrlError`` si à risque.

    Exige un schéma http(s) et un hôte, refuse ``localhost`` et toute IP résolue interne
    (privée/boucle/lien-local/réservée/multicast). Résolution via ``resolve`` (injectable).
    """
    resolve = resolve or _default_resolve
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsupportedUrlError(
            f"schéma non supporté : {parsed.scheme or '(aucun)'} (http/https attendu)"
        )
    host = parsed.hostname
    if not host:
        raise UnsupportedUrlError("URL sans hôte")
    if host.lower() == "localhost":
        raise UnsupportedUrlError("cible interne refusée : localhost")
    try:
        ips = resolve(host)
    except OSError as exc:
        raise UrlUnreachableError(f"résolution DNS impossible pour {host!r}") from exc
    if not ips:
        raise UrlUnreachableError(f"aucune adresse résolue pour {host!r}")
    for ip in ips:
        if _is_blocked_ip(ip):
            raise UnsupportedUrlError(f"cible interne refusée ({host} → {ip})")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Revalide chaque cible de redirection (refus SSRF à chaque saut).

    Sans cela, une page publique passant ``assert_safe_url`` pourrait répondre ``302
    Location: http://169.254.169.254/…`` (ou ``127.0.0.1``) et ``urllib`` suivrait la
    redirection vers la cible interne, contournant le filtre. On rejoue donc la validation
    sur chaque nouvelle URL ; un refus propage ``UnsupportedUrlError`` hors de l'ouverture.
    """

    def __init__(self, resolve: Resolver) -> None:
        self._resolve = resolve

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_safe_url(newurl, resolve=self._resolve)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _decode_body(raw: bytes, charset: str) -> str:
    """Décode ``raw`` selon ``charset`` ; repli ``utf-8`` si le charset annoncé est inconnu.

    Un en-tête ``Content-Type: …; charset=bidon`` ferait lever ``LookupError`` à ``decode``
    (le codec est introuvable, ``errors="replace"`` n'y change rien) ; on retombe alors sur
    utf-8 tolérant plutôt que de laisser remonter une erreur non typée (500 non géré).
    """
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _make_default_transport(resolve: Resolver) -> Transport:
    """Transport réel ``urllib`` (revalidation SSRF sur chaque redirection via ``resolve``)."""
    opener = urllib.request.build_opener(_SafeRedirectHandler(resolve))

    def _transport(url: str, timeout: int) -> tuple[str, str]:
        request = urllib.request.Request(
            url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"}
        )
        with opener.open(request, timeout=timeout) as response:  # noqa: S310 - schéma validé en amont
            charset = response.headers.get_content_charset() or "utf-8"
            raw = response.read(_MAX_BYTES)
            return _decode_body(raw, charset), (response.headers.get_content_type() or "")

    return _transport


def fetch_html(
    url: str,
    *,
    transport: Transport | None = None,
    resolve: Resolver | None = None,
    timeout: int = DEFAULT_FETCH_TIMEOUT,
) -> HtmlDocument:
    """Récupère le HTML d'une ``url`` ; convertit les échecs en erreurs typées.

    Valide l'URL (SSRF) **avant** l'appel, puis délègue au ``transport`` (injectable). Mappe
    404/410 → ``UrlUnreachableError``, 403/429 → ``BlockedError``, timeout/DNS/réseau →
    ``UrlUnreachableError``, corps vide → ``EmptyContentError``.
    """
    if not isinstance(url, str) or url.strip() == "":
        raise UnsupportedUrlError("URL vide")
    url = url.strip()
    resolve = resolve or _default_resolve
    assert_safe_url(url, resolve=resolve)
    transport = transport or _make_default_transport(resolve)
    try:
        body, content_type = transport(url, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise BlockedError(f"accès refusé par la cible (HTTP {exc.code})") from exc
        raise UrlUnreachableError(f"URL injoignable (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UrlUnreachableError(f"URL injoignable : {url}") from exc
    if not body or body.strip() == "":
        raise EmptyContentError(f"réponse vide pour {url}")
    return HtmlDocument(url=url, html=body, content_type=content_type)
