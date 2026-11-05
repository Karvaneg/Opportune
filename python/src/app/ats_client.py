"""Client HTTP des API publiques d'ATS : Greenhouse et Lever (OPP-226).

Ces API servent, **sans clé**, les offres qu'une entreprise a publiées sur sa page carrière :

- Greenhouse : ``GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true``
  (``content=true`` ajoute la description complète, les départements et les bureaux) ;
- Lever : ``GET https://api.lever.co/v0/postings/{site}?mode=json`` (``api.eu.lever.co`` pour
  les comptes hébergés en Europe).

Opportune ne fait que **lire** (RG-23) : l'API de candidature de ces ATS n'est jamais appelée.
Le transport est **injectable** (tests sans réseau) ; les échecs deviennent des erreurs typées :
``AtsNotFoundError`` (404, entreprise inconnue de l'ATS), ``AtsRateLimitError`` (429),
``AtsUnavailableError`` (réseau, 5xx), ``AtsError`` pour le reste (statut inattendu, JSON
illisible).
"""

from __future__ import annotations

import json
from typing import Callable
from urllib.parse import quote

from app.http_get import HttpResponse, HttpUnavailableError, http_get
from app.ats_company import GREENHOUSE, LEVER, AtsCompany

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"
LEVER_API = "https://api.lever.co/v0/postings"
LEVER_EU_API = "https://api.eu.lever.co/v0/postings"

# Délai d'un appel (secondes) : une liste d'offres complète tient en une seule réponse.
DEFAULT_TIMEOUT = 20

# User-Agent qui identifie Opportune (RG-21) : on ne se fait pas passer pour un navigateur.
USER_AGENT = (
    "Opportune/1.0 (assistant de candidature local; +https://github.com/Karvaneg/Opportune)"
)

ATS_LABELS = {GREENHOUSE: "Greenhouse", LEVER: "Lever"}

# Transport : (url) -> HttpResponse. Les statuts HTTP d'erreur sont rendus (pas levés) ; seule
# une panne réseau (y compris pendant la lecture de la réponse) lève ``AtsUnavailableError``.
Transport = Callable[[str], HttpResponse]


class AtsError(Exception):
    """Échec d'un appel à l'API d'un ATS."""


class AtsNotFoundError(AtsError):
    """L'ATS ne connaît pas cet identifiant d'entreprise (HTTP 404)."""


class AtsRateLimitError(AtsError):
    """L'ATS limite le débit (HTTP 429) : on n'insiste pas pendant la passe."""


class AtsUnavailableError(AtsError):
    """L'API de l'ATS n'a pu être atteinte : DNS, timeout, coupure réseau ou 5xx."""


def _default_transport(url: str) -> HttpResponse:
    """Transport réel : un GET JSON identifié (cf. ``app.http_get``)."""
    try:
        return http_get(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
        )
    except HttpUnavailableError as exc:
        raise AtsUnavailableError(f"API injoignable : {exc}") from exc


def jobs_url(company: AtsCompany, *, with_content: bool = True) -> str:
    """URL de l'API qui liste les offres publiées de l'entreprise.

    ``with_content=False`` évite à Greenhouse de renvoyer la description complète de chaque
    offre (réponse bien plus légère) : utile quand on ne fait que compter les offres. Le lieu
    (``location.name``) reste fourni ; seuls les bureaux (``offices``) manquent. Lever n'a pas
    d'équivalent : sa réponse est la même dans les deux cas.
    """
    slug = quote(company.slug, safe="")
    if company.ats == GREENHOUSE:
        query = "?content=true" if with_content else ""
        return f"{GREENHOUSE_API}/{slug}/jobs{query}"
    base = LEVER_EU_API if company.eu else LEVER_API
    return f"{base}/{slug}?mode=json"


class AtsClient:
    """Lit la liste des offres publiées d'une entreprise sur son ATS (transport injectable)."""

    def __init__(self, *, transport: Transport | None = None) -> None:
        self._transport = transport or _default_transport

    def list_jobs(self, company: AtsCompany, *, with_content: bool = True) -> list[dict]:
        """Offres publiées de l'entreprise (JSON brut de l'ATS) ; lève une ``AtsError`` typée.

        ``with_content=False`` : liste allégée, sans descriptions (cf. ``jobs_url``).
        """
        label = ATS_LABELS.get(company.ats, company.ats)
        response = self._transport(jobs_url(company, with_content=with_content))
        if response.status == 404:
            raise AtsNotFoundError(f"entreprise introuvable sur {label} : {company.slug}")
        if response.status == 429:
            raise AtsRateLimitError(f"{label} limite les requêtes (HTTP 429) : {company.slug}")
        if response.status >= 500:
            raise AtsUnavailableError(f"{label} indisponible (HTTP {response.status})")
        if response.status != 200:
            raise AtsError(f"{label} a répondu HTTP {response.status} pour {company.slug}")
        try:
            payload = json.loads(response.body or "null")
        except json.JSONDecodeError as exc:
            raise AtsError(f"réponse {label} illisible pour {company.slug}") from exc
        # Greenhouse enveloppe la liste dans ``{"jobs": [...]}`` ; Lever rend la liste nue.
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            raise AtsError(f"réponse {label} inattendue pour {company.slug}")
        return [job for job in jobs if isinstance(job, dict)]
