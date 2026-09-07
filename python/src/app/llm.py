"""Configuration de l'accès au LLM local via Ollama (V2, OPP-073).

Configure la connexion à un serveur Ollama et le modèle par défaut (Ministral, un
modèle Mistral servi localement), et fournit un client de génération minimal. Aucune
logique métier n'est branchée : c'est la configuration de l'accès au modèle, pas
encore son usage applicatif.

Le transport HTTP est **injectable** : par défaut un POST via la bibliothèque
standard (``urllib``) — aucune dépendance externe ; en test, on injecte un transport
factice pour éviter tout appel réseau et tout serveur Ollama en cours d'exécution.
"""

from __future__ import annotations

import json
import os
import urllib.request
from functools import partial
from typing import Callable

# Hôte du serveur Ollama et modèle par défaut, surchargeables par variables d'env
# (voir docker-compose : OLLAMA_HOST pointe sur l'Ollama natif de l'hôte via
# `host.docker.internal`, OLLAMA_MODEL sur le modèle installé).
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "ministral-3:3b")

# Délai maximal (secondes) d'un appel au serveur Ollama.
DEFAULT_TIMEOUT = 60

# Un transport prend (url, payload) et retourne le corps de réponse décodé (dict).
Transport = Callable[[str, dict], dict]


def build_generate_request(prompt: str, *, model: str | None = None, host: str | None = None):
    """Construit l'URL et la charge utile d'une génération Ollama (``/api/generate``).

    Pur (aucun appel réseau), donc directement testable. Lève ``ValueError`` si le
    prompt est vide.
    """
    if not isinstance(prompt, str) or prompt.strip() == "":
        raise ValueError("Le prompt est requis")

    url = f"{(host or DEFAULT_OLLAMA_HOST).rstrip('/')}/api/generate"
    payload = {"model": model or DEFAULT_MODEL, "prompt": prompt, "stream": False}
    return url, payload


def _urllib_transport(url: str, payload: dict, *, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Transport par défaut : POST JSON via ``urllib``, retourne la réponse décodée."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (URL interne)
        return json.loads(response.read().decode("utf-8"))


def default_transport(*, timeout: int = DEFAULT_TIMEOUT) -> Transport:
    """Fabrique le transport HTTP par défaut (POST ``urllib``) lié à un ``timeout``.

    Point d'entrée **public** pour obtenir le transport réel sans dépendre du détail
    d'implémentation ``_urllib_transport`` : les consommateurs (p. ex.
    ``app.llm_client``) restent découplés de la fonction interne.
    """
    return partial(_urllib_transport, timeout=timeout)


def generate(
    prompt: str,
    *,
    model: str | None = None,
    host: str | None = None,
    transport: Transport | None = None,
) -> str:
    """Génère une réponse du modèle pour un ``prompt``.

    ``transport`` est injectable (``(url, payload) -> dict``) : par défaut, un POST
    HTTP réel vers Ollama. Retourne le texte généré (champ ``response`` de la réponse
    Ollama), ou une chaîne vide s'il est absent.
    """
    url, payload = build_generate_request(prompt, model=model, host=host)
    send = transport or _urllib_transport
    result = send(url, payload)
    return result.get("response", "")
