"""Transport Discord (V2, OPP-117) — envoi de messages via l'API REST.

Zéro dépendance : POST ``urllib`` vers l'API Discord. Le transport est un **contrat**
injectable (comme ``LLMClient``, OPP-079) : en test, un ``MockDiscordTransport`` sans
réseau ; en production, ``HttpDiscordTransport`` adossé à ``urllib``.

Le token du bot est lu depuis l'environnement (``DISCORD_BOT_TOKEN``), jamais codé en
dur, et n'est présent que dans l'en-tête ``Authorization`` de la requête sortante.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

# Base de l'API REST Discord (versionnée) et délai maximal d'un appel.
DISCORD_API_BASE = "https://discord.com/api/v10"
DEFAULT_TIMEOUT = 15


class DiscordError(Exception):
    """Échec d'un appel à l'API Discord."""


class DiscordTimeoutError(DiscordError):
    """L'API Discord n'a pas répondu dans le délai imparti."""


def build_send_request(
    channel_id: str, message: dict, *, token: str, base: str = DISCORD_API_BASE
) -> tuple[str, bytes, dict]:
    """Construit l'URL, le corps et les en-têtes d'un envoi de message (pur).

    Aucun appel réseau : directement testable. Lève ``ValueError`` si ``channel_id``
    ou ``token`` est vide.
    """
    if not isinstance(channel_id, str) or channel_id.strip() == "":
        raise ValueError("channel_id est requis")
    if not isinstance(token, str) or token.strip() == "":
        raise ValueError("token est requis")
    url = f"{base.rstrip('/')}/channels/{channel_id}/messages"
    data = json.dumps(message).encode("utf-8")
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }
    return url, data, headers


@runtime_checkable
class DiscordTransport(Protocol):
    """Contrat d'envoi de message consommé par la revue Discord.

    Une seule opération : poster un ``message`` (payload Discord déjà construit) dans un
    salon et retourner le corps de réponse (dont l'``id`` du message créé).
    """

    def send_message(self, channel_id: str, message: dict) -> dict: ...


class HttpDiscordTransport:
    """Implémentation réelle du contrat, adossée à ``urllib`` (zéro dépendance).

    Le token est fourni explicitement ou lu depuis ``DISCORD_BOT_TOKEN``. Les échecs
    réseau sont convertis en erreurs typées du contrat.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        base: str = DISCORD_API_BASE,
    ) -> None:
        # Repli sur l'environnement uniquement si aucun token n'est fourni (``None``) ;
        # un token explicitement vide est honoré tel quel (pas de repli silencieux).
        self._token = token if token is not None else os.environ.get("DISCORD_BOT_TOKEN")
        self._timeout = timeout
        self._base = base

    def send_message(self, channel_id: str, message: dict) -> dict:
        if not self._token:
            raise DiscordError("Token Discord absent (DISCORD_BOT_TOKEN)")
        url, data, headers = build_send_request(
            channel_id, message, token=self._token, base=self._base
        )
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except TimeoutError as exc:
            raise DiscordTimeoutError(f"Délai dépassé ({self._timeout}s) pour {url}") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise DiscordTimeoutError(f"Délai dépassé pour {url}") from exc
            raise DiscordError(f"Échec de l'appel Discord vers {url}") from exc
        except OSError as exc:
            raise DiscordError(f"Échec de l'appel Discord vers {url}") from exc


class MockDiscordTransport:
    """Implémentation de test du contrat, sans réseau.

    Enregistre les messages envoyés dans ``sent`` et retourne une réponse scriptée
    (par défaut un ``id`` de message stable). On peut lui passer une exception à lever
    (``error``) pour exercer la gestion d'erreur côté appelant.
    """

    def __init__(
        self, *, message_id: str = "msg-1", error: Exception | None = None
    ) -> None:
        self._message_id = message_id
        self.error = error
        self.sent: list[dict] = []

    def send_message(self, channel_id: str, message: dict) -> dict:
        if not isinstance(channel_id, str) or channel_id.strip() == "":
            raise ValueError("channel_id est requis")
        self.sent.append({"channel_id": channel_id, "message": message})
        if self.error is not None:
            raise self.error
        return {"id": self._message_id, "channel_id": channel_id}
