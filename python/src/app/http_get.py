"""GET HTTP JSON avec ``urllib``, partagé par les clients d'API d'offres (Adzuna, ATS).

Les statuts d'erreur HTTP sont **rendus** dans une ``HttpResponse`` (pas levés) pour que chaque
client décide par statut. Une panne de transport, y compris pendant la lecture du corps, lève
``HttpUnavailableError`` : chaque client la traduit dans son erreur « API injoignable ».
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class HttpResponse:
    """Réponse HTTP brute vue par le client, indépendante du transport sous-jacent."""

    status: int
    body: str


class HttpUnavailableError(Exception):
    """L'API n'a pu être atteinte : DNS, timeout, connexion coupée, TLS ou réponse tronquée."""


# ``OSError`` couvre DNS, timeout, connexion coupée et TLS (``URLError``, ``TimeoutError``,
# ``ConnectionResetError``, ``ssl.SSLError``) ; ``HTTPException`` couvre une réponse tronquée
# (``IncompleteRead``).
_TRANSPORT_ERRORS = (OSError, http.client.HTTPException)


def http_get(url: str, *, headers: Mapping[str, str], timeout: float) -> HttpResponse:
    """Exécute un GET et rend statut + corps décodé ; lève ``HttpUnavailableError`` si panne."""
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        # Les appelants construisent l'URL sur des hôtes d'API fixes (pas de SSRF).
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return HttpResponse(response.status, response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        except _TRANSPORT_ERRORS:
            body = ""
        return HttpResponse(exc.code, body)
    except _TRANSPORT_ERRORS as exc:
        raise HttpUnavailableError(str(exc)) from exc
