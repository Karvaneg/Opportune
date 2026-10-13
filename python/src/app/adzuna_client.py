"""Client bas niveau de l'API Adzuna « Job Search » (V1, OPP-120).

Connecteur de collecte **actif** d'Opportune (France Travail étant passé sur accès restreint) :
parle à l'API Adzuna derrière un **transport HTTP injectable** (défaut ``urllib``), donc
testable **sans réseau**. Plus simple que France Travail : pas d'OAuth — ``app_id`` et
``app_key`` accompagnent chaque requête en paramètres. Une recherche cible un pays
(``fr``), filtre les offres (mots-clés, lieu, contrat permanent ≈ CDI) et pagine par **numéro
de page** (1-indexé dans le chemin).

Les échecs sont convertis en **erreurs typées** (``AdzunaAuthError`` sur 401/403,
``AdzunaQuotaError`` sur 429, ``AdzunaUnavailableError`` sur panne réseau/5xx), pour que le
pipeline de collecte les range dans ``source_error`` plutôt que de les avaler. Le total de
résultats est renvoyé dans le corps (champ ``count``), ce qui pilote la pagination côté
``adzuna_source``.

Note : Adzuna ne renvoie qu'un **extrait** de la description de l'offre — suffisant pour
l'analyse d'intake, qui ré-exploite ensuite ce texte via le socle OPP-119.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlencode

# Base de l'API Job Search ; le pays et le numéro de page complètent le chemin. Surchargeable
# à la construction (tests, bac à sable).
BASE_URL = "https://api.adzuna.com/v1/api/jobs"
# Pays par défaut (marché français).
DEFAULT_COUNTRY = "fr"
# Nombre de résultats par page maximal accepté par l'API.
RESULTS_PER_PAGE_MAX = 50

# Délai par défaut d'un appel (secondes) : court, un appel qui traîne ne doit pas bloquer la passe.
DEFAULT_TIMEOUT = 20


class AdzunaError(Exception):
    """Échec d'un appel à l'API Adzuna (erreur de base du contrat)."""


class AdzunaAuthError(AdzunaError):
    """Identifiants manquants ou refusés (401/403) : ``app_id`` / ``app_key`` invalides."""


class AdzunaQuotaError(AdzunaError):
    """Quota dépassé (HTTP 429) : plan gratuit limité (2 500 appels/mois, 250/jour)."""


class AdzunaUnavailableError(AdzunaError):
    """L'API n'a pu être atteinte : DNS, timeout, coupure réseau ou 5xx."""


@dataclass(frozen=True)
class HttpResponse:
    """Réponse HTTP brute vue par le client, indépendante du transport sous-jacent."""

    status: int
    body: str


# Transport : (url) -> HttpResponse. Les statuts d'erreur HTTP sont rendus comme des
# ``HttpResponse`` (pas levés) pour que la logique par statut reste dans le client ; seule une
# panne réseau lève ``AdzunaUnavailableError``.
Transport = Callable[[str], HttpResponse]


@dataclass(frozen=True)
class AdzunaCredentials:
    """Identifiants d'application Adzuna (obtenus sur developer.adzuna.com)."""

    app_id: str
    app_key: str


def credentials_from_env(env: Mapping[str, str]) -> AdzunaCredentials:
    """Lit les identifiants depuis l'environnement ; lève si l'un manque.

    Attend ``ADZUNA_APP_ID`` et ``ADZUNA_APP_KEY`` (inscription gratuite sur
    developer.adzuna.com). Absents ou vides → ``AdzunaAuthError`` explicite : on refuse de
    construire un client qui ne pourra pas s'authentifier.
    """
    app_id = (env.get("ADZUNA_APP_ID") or "").strip()
    app_key = (env.get("ADZUNA_APP_KEY") or "").strip()
    if not app_id or not app_key:
        raise AdzunaAuthError(
            "ADZUNA_APP_ID / ADZUNA_APP_KEY manquants : inscrivez-vous sur "
            "developer.adzuna.com et renseignez-les dans l'environnement."
        )
    return AdzunaCredentials(app_id=app_id, app_key=app_key)


@dataclass(frozen=True)
class SearchPage:
    """Une page de résultats : les offres brutes et le total réel annoncé (``count``)."""

    offers: tuple[dict, ...]
    total: int


def _default_transport(url: str) -> HttpResponse:
    """Transport réel ``urllib`` : exécute un GET, rend un ``HttpResponse``.

    Les statuts d'erreur HTTP (``HTTPError``) sont convertis en ``HttpResponse`` pour que le
    client décide par statut. Une panne de transport (DNS, timeout, connexion) lève
    ``AdzunaUnavailableError`` — il n'y a pas de statut à inspecter.
    """
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        # URL = endpoint officiel https, pas une URL arbitraire utilisateur (pas de SSRF).
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:  # noqa: S310
            return HttpResponse(response.status, response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return HttpResponse(exc.code, exc.read().decode("utf-8", errors="replace") if exc.fp else "")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AdzunaUnavailableError(f"API Adzuna injoignable : {exc}") from exc


class AdzunaClient:
    """Recherche paginée d'offres Adzuna (identifiants en paramètres, transport injectable)."""

    def __init__(
        self,
        credentials: AdzunaCredentials,
        *,
        transport: Transport | None = None,
        base_url: str = BASE_URL,
        country: str = DEFAULT_COUNTRY,
    ) -> None:
        self._credentials = credentials
        self._transport = transport or _default_transport
        self._base_url = base_url
        self._country = country

    def search(
        self,
        *,
        page: int,
        results_per_page: int,
        extra_params: "Mapping[str, str] | None" = None,
    ) -> SearchPage:
        """Récupère une page d'offres (``page`` 1-indexée) ; retourne offres + total.

        ``429`` lève ``AdzunaQuotaError``, ``401``/``403`` ``AdzunaAuthError`` ; tout autre
        statut non-200 lève ``AdzunaError``. ``extra_params`` (``what``, ``where``,
        ``permanent``…) est fusionné tel quel dans la requête.
        """
        params = {
            "app_id": self._credentials.app_id,
            "app_key": self._credentials.app_key,
            "results_per_page": str(results_per_page),
            "content-type": "application/json",
        }
        if extra_params:
            params.update(extra_params)
        url = f"{self._base_url}/{self._country}/search/{page}?{urlencode(params)}"
        response = self._transport(url)
        if response.status == 429:
            raise AdzunaQuotaError("quota dépassé (HTTP 429)")
        if response.status in (401, 403):
            raise AdzunaAuthError(f"identifiants refusés (HTTP {response.status})")
        if response.status != 200:
            raise AdzunaError(f"recherche échouée (HTTP {response.status})")
        try:
            payload = json.loads(response.body or "{}")
        except json.JSONDecodeError as exc:
            raise AdzunaError("réponse de recherche illisible") from exc
        offers = tuple(payload.get("results") or ())
        # ``count`` est le total réel annoncé ; Adzuna le renvoie tantôt entier, tantôt
        # flottant. On accepte les deux (bool exclu) ; absent/illisible → repli sur ce qu'on a vu.
        total = payload.get("count")
        usable_total = isinstance(total, (int, float)) and not isinstance(total, bool)
        return SearchPage(offers=offers, total=int(total) if usable_total else len(offers))
