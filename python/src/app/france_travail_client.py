"""Client bas niveau de l'API France Travail « Offres d'emploi v2 » (V1, OPP-120).

Premier connecteur réel de collecte : parle à l'API officielle France Travail, derrière un
**transport HTTP injectable** (défaut ``urllib``, zéro dépendance) — fidèle à la stack
(``llm``, ``url_fetch``) et donc testable **sans réseau**. Deux responsabilités, et deux
seulement : obtenir un jeton OAuth2 (``client_credentials``) et interroger ``/offres/search``
avec pagination. Il ne connaît **ni** le port ``SourceOffres`` **ni** le modèle ``Offer`` :
l'adaptation vers une ``RawOffer`` est l'affaire de ``france_travail_source``.

Les échecs sont convertis en **erreurs typées** : un défaut d'authentification
(``FranceTravailAuthError``), un dépassement de quota (``FranceTravailQuotaError``, HTTP 429)
et l'indisponibilité réseau (``FranceTravailUnavailableError``) sont distingués, pour que le
pipeline de collecte (``collect_offers``) les range dans ``source_error`` plutôt que de les
avaler.

**Pagination.** L'API borne une requête : ``range=p-d`` (≤ 150 par page) et une **fenêtre**
dure (premier élément ≤ 1000, second ≤ 1149, soit ~1150 offres accessibles). Le total réel
est renvoyé dans l'en-tête ``Content-Range: offres p-d/total`` ; ``206 Partial Content`` est
donc un **succès** (une page parmi d'autres), ``204`` une page vide. La traversée de la
fenêtre est pilotée par ``france_travail_source``, qui enchaîne les pages.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlencode

# Endpoints officiels. L'OAuth2 partenaire exige le realm en query ; la recherche vit sur le
# domaine ``api.francetravail.io``. Surchargeables à la construction (tests, bac à sable).
AUTH_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
# Scope requis par l'API Offres d'emploi v2 (les deux jetons, séparés par une espace).
SCOPE = "api_offresdemploiv2 o2dsoffre"

# Taille de page maximale imposée par l'API (range de 150 éléments : ``0-149``).
PAGE_SIZE_MAX = 150
# Fenêtre dure de l'API : un ``range=p-d`` est refusé (400) si ``p`` dépasse 1000 ou si ``d``
# dépasse 1149. On peut donc lire au plus ~1150 offres par requête ; dépasser exigerait de
# fragmenter par date/département (hors périmètre OPP-120, voir les critères du ticket).
RANGE_START_MAX = 1000
RANGE_END_MAX = 1149
WINDOW_MAX = RANGE_END_MAX + 1  # 1150 offres accessibles au total


class FranceTravailError(Exception):
    """Échec d'un appel à l'API France Travail (erreur de base du contrat)."""


class FranceTravailAuthError(FranceTravailError):
    """Authentification impossible : identifiants manquants/refusés, jeton non délivré."""


class FranceTravailQuotaError(FranceTravailError):
    """Quota dépassé (HTTP 429) : l'API impose un rate limit (10 appels/s)."""


class FranceTravailUnavailableError(FranceTravailError):
    """L'API n'a pu être atteinte : DNS, timeout, coupure réseau ou 5xx."""


@dataclass(frozen=True)
class HttpResponse:
    """Réponse HTTP brute vue par le client, indépendante du transport sous-jacent."""

    status: int
    headers: Mapping[str, str]
    body: str


# Transport : (méthode, url, en-têtes, corps) -> HttpResponse. Les statuts d'erreur HTTP
# (400/429…) sont rendus comme des ``HttpResponse`` (pas levés) pour que la logique par statut
# reste dans le client ; seule une panne réseau lève ``FranceTravailUnavailableError``.
Transport = Callable[[str, str, Mapping[str, str], "str | None"], HttpResponse]

# Délai par défaut d'un appel (secondes) : court, l'API répond vite ; un appel qui traîne ne
# doit pas bloquer une passe de collecte.
DEFAULT_TIMEOUT = 20


@dataclass(frozen=True)
class FranceTravailCredentials:
    """Identifiants OAuth2 d'une application France Travail (``client_credentials``)."""

    client_id: str
    client_secret: str


def credentials_from_env(env: Mapping[str, str]) -> FranceTravailCredentials:
    """Lit les identifiants depuis l'environnement ; lève si l'un manque.

    Attend ``FRANCE_TRAVAIL_CLIENT_ID`` et ``FRANCE_TRAVAIL_CLIENT_SECRET`` (créés sur
    francetravail.io). Absents ou vides → ``FranceTravailAuthError`` explicite : on refuse de
    construire un client qui ne pourra de toute façon pas s'authentifier.
    """
    client_id = (env.get("FRANCE_TRAVAIL_CLIENT_ID") or "").strip()
    client_secret = (env.get("FRANCE_TRAVAIL_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        raise FranceTravailAuthError(
            "FRANCE_TRAVAIL_CLIENT_ID / FRANCE_TRAVAIL_CLIENT_SECRET manquants : "
            "créez une application sur francetravail.io et renseignez-les dans l'environnement."
        )
    return FranceTravailCredentials(client_id=client_id, client_secret=client_secret)


@dataclass(frozen=True)
class SearchPage:
    """Une page de résultats de recherche : les offres brutes et le total réel annoncé.

    ``offers`` sont les dictionnaires JSON tels que renvoyés par l'API (``resultats``).
    ``total`` est le nombre total d'offres correspondant à la requête (lu dans l'en-tête
    ``Content-Range``), qui sert à savoir s'il reste des pages à récupérer.
    """

    offers: tuple[dict, ...]
    total: int


def _default_transport(
    method: str, url: str, headers: Mapping[str, str], body: "str | None"
) -> HttpResponse:
    """Transport réel ``urllib`` : exécute la requête, rend un ``HttpResponse``.

    Les statuts d'erreur HTTP (``HTTPError``) sont convertis en ``HttpResponse`` pour que le
    client décide par statut (429 quota, 4xx auth…). Une panne de transport (DNS, timeout,
    connexion) lève ``FranceTravailUnavailableError`` — il n'y a pas de statut à inspecter.
    """
    data = body.encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
    try:
        # Endpoint officiel http(s), pas une URL arbitraire utilisateur (pas de risque SSRF).
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
            return HttpResponse(response.status, dict(response.headers), raw)
    except urllib.error.HTTPError as exc:  # statut d'erreur : on le rend, le client tranche
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return HttpResponse(exc.code, dict(exc.headers or {}), raw)
    except (urllib.error.URLError, TimeoutError) as exc:  # panne réseau : pas de statut
        raise FranceTravailUnavailableError(f"API France Travail injoignable : {exc}") from exc


def _header(headers: Mapping[str, str], name: str) -> "str | None":
    """Lit un en-tête sans dépendre de la casse.

    Le transport réel rend les en-têtes en ``dict`` simple (``dict(response.headers)``), ce qui
    perd l'insensibilité à la casse qu'offrait ``http.client.HTTPMessage`` : une réponse qui
    renverrait ``content-range`` en minuscules deviendrait introuvable et tronquerait la
    pagination. On compare donc les clés en minuscules.
    """
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _parse_total(content_range: "str | None", *, fallback: int) -> int:
    """Extrait le total de l'en-tête ``Content-Range: offres p-d/total`` ; repli sinon.

    L'API annonce ``offres 0-149/1234`` : le total suit le ``/``. Absent, mal formé ou ``*``
    (total inconnu) → ``fallback`` (typiquement ce qu'on a déjà vu), de sorte que la
    pagination s'arrête proprement plutôt que de boucler sur un total fantaisiste.
    """
    if not content_range or "/" not in content_range:
        return fallback
    total_part = content_range.rsplit("/", 1)[1].strip()
    try:
        return int(total_part)
    except ValueError:
        return fallback


class FranceTravailClient:
    """Accès OAuth2 + recherche paginée à l'API Offres d'emploi v2 (transport injectable)."""

    def __init__(
        self,
        credentials: FranceTravailCredentials,
        *,
        transport: Transport | None = None,
        auth_url: str = AUTH_URL,
        search_url: str = SEARCH_URL,
    ) -> None:
        self._credentials = credentials
        self._transport = transport or _default_transport
        self._auth_url = auth_url
        self._search_url = search_url

    def fetch_token(self) -> str:
        """Obtient un jeton d'accès via le flux ``client_credentials``.

        Lève ``FranceTravailQuotaError`` sur 429, ``FranceTravailAuthError`` sur tout autre
        statut non-200 ou si la réponse ne porte pas d'``access_token``.
        """
        body = urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self._credentials.client_id,
                "client_secret": self._credentials.client_secret,
                "scope": SCOPE,
            }
        )
        response = self._transport(
            "POST",
            self._auth_url,
            {"Content-Type": "application/x-www-form-urlencoded"},
            body,
        )
        if response.status == 429:
            raise FranceTravailQuotaError("quota dépassé à l'authentification (HTTP 429)")
        if response.status != 200:
            raise FranceTravailAuthError(
                f"authentification refusée (HTTP {response.status})"
            )
        try:
            token = json.loads(response.body).get("access_token")
        except (json.JSONDecodeError, AttributeError) as exc:
            raise FranceTravailAuthError("réponse OAuth2 illisible") from exc
        if not token:
            raise FranceTravailAuthError("réponse OAuth2 sans access_token")
        return token

    def search(
        self,
        *,
        token: str,
        start: int,
        end: int,
        type_contrat: str = "CDI",
        extra_params: "Mapping[str, str] | None" = None,
    ) -> SearchPage:
        """Récupère une page d'offres (``range=start-end``) filtrées par type de contrat.

        ``200``/``206`` sont des succès (page pleine ou partielle), ``204`` une page vide
        (fin de pagination). ``429`` lève ``FranceTravailQuotaError`` ; tout autre statut lève
        ``FranceTravailError``. ``extra_params`` (mots-clés, code ROME, commune…) est fusionné
        tel quel dans la requête.
        """
        params = {"typeContrat": type_contrat, "range": f"{start}-{end}"}
        if extra_params:
            params.update(extra_params)
        url = f"{self._search_url}?{urlencode(params)}"
        response = self._transport(
            "GET",
            url,
            {"Authorization": f"Bearer {token}", "Accept": "application/json"},
            None,
        )
        if response.status == 204:
            return SearchPage(offers=(), total=0)
        if response.status == 429:
            raise FranceTravailQuotaError("quota dépassé à la recherche (HTTP 429)")
        if response.status not in (200, 206):
            raise FranceTravailError(f"recherche échouée (HTTP {response.status})")
        try:
            payload = json.loads(response.body or "{}")
        except json.JSONDecodeError as exc:
            raise FranceTravailError("réponse de recherche illisible") from exc
        offers = tuple(payload.get("resultats") or ())
        total = _parse_total(_header(response.headers, "Content-Range"), fallback=start + len(offers))
        return SearchPage(offers=offers, total=total)
