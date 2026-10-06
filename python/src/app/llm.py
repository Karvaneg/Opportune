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
from typing import Callable, Mapping

# Hôte du serveur Ollama et modèle par défaut, surchargeables par variables d'env
# (voir docker-compose : OLLAMA_HOST pointe sur l'Ollama natif de l'hôte via
# `host.docker.internal`, OLLAMA_MODEL sur le modèle installé).
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "ministral-3:3b")


def _env_int(name: str, default: int) -> int:
    """Lit un entier strictement positif depuis l'env, défaut sinon (tolérant).

    Absent, vide, non entier ou non positif → ``default``. Choix volontairement
    *tolérant* (pas de ``raise``) : ce sont des paramètres de confort/perf, pas de
    sécurité — une valeur mal saisie ne doit jamais empêcher l'API de démarrer.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


# Délai maximal (secondes) d'un appel au serveur Ollama : défaut *brut* de la
# bibliothèque. Les appels métier réels (intake, lettre) passent par
# ``resolve_llm_timeout`` qui impose un délai bien plus généreux (cf. ci-dessous).
DEFAULT_TIMEOUT = 60

# Délai LLM « généreux » des appels métier (secondes), surchargeable par
# ``OPPORTUNE_LLM_TIMEOUT``. Défaut 300 : une lettre dépasse 60 s à froid, et un intake
# d'offre réaliste en sortie structurée ~85 s avec ministral-3:3b (cf. [[ollama-wsl2-acces]]).
DEFAULT_LLM_TIMEOUT = 300

# Plafond de tokens générés (``num_predict`` d'Ollama), surchargeable par
# ``OLLAMA_NUM_PREDICT`` (OPP-154). C'est un *plafond* anti-emballement, pas une cible :
# chaque appel s'arrête de lui-même à l'EOS bien avant (JSON d'intake clos, lettre finie).
# Le **même** client sert l'intake ET la rédaction de lettre : on dimensionne donc sur la
# sortie la plus **longue** — la lettre (~1000 tokens à froid) — et non sur le JSON d'intake,
# sinon une lettre légitime serait tronquée. 2048 laisse une marge franche tout en bornant
# une vraie génération qui s'emballe.
DEFAULT_NUM_PREDICT = _env_int("OLLAMA_NUM_PREDICT", 2048)


def resolve_llm_timeout(env: Mapping[str, str]) -> int:
    """Lit ``OPPORTUNE_LLM_TIMEOUT`` (secondes) ; ``DEFAULT_LLM_TIMEOUT`` si absent.

    Absent/vide → défaut généreux. Toute valeur non entière ou non strictement positive →
    ``ValueError`` explicite : on refuse de démarrer sur un timeout ambigu plutôt que de
    recâbler silencieusement le défaut 60 s trop court. Home partagé par tous les appels LLM
    (runner push, intake de profil, intake d'offre) — câblé via ``OllamaLLMClient(timeout=…)``.
    """
    raw = env.get("OPPORTUNE_LLM_TIMEOUT")
    if raw is None or raw == "":
        return DEFAULT_LLM_TIMEOUT
    try:
        timeout = int(raw)
    except ValueError:
        raise ValueError(
            f"OPPORTUNE_LLM_TIMEOUT invalide ({raw!r}) : entier positif de secondes attendu."
        ) from None
    if timeout <= 0:
        raise ValueError(
            f"OPPORTUNE_LLM_TIMEOUT invalide ({timeout}) : doit être strictement positif."
        )
    return timeout

# Un transport prend (url, payload) et retourne le corps de réponse décodé (dict).
Transport = Callable[[str, dict], dict]


def build_generate_request(
    prompt: str,
    *,
    model: str | None = None,
    host: str | None = None,
    fmt: object | None = None,
    num_predict: int | None = None,
):
    """Construit l'URL et la charge utile d'une génération Ollama (``/api/generate``).

    ``fmt`` (optionnel) contraint le décodage : ``"json"`` force une syntaxe JSON valide,
    un dict force un schéma JSON (clés + types), cf. « structured outputs » d'Ollama. Absent
    → aucun champ ``format`` dans la charge (génération de texte libre, comportement d'origine).

    ``num_predict`` (optionnel) borne le nombre de tokens générés via ``options.num_predict``
    d'Ollama. Absent → aucune borne (comportement d'origine).

    Pur (aucun appel réseau), donc directement testable. Lève ``ValueError`` si le
    prompt est vide.
    """
    if not isinstance(prompt, str) or prompt.strip() == "":
        raise ValueError("Le prompt est requis")

    url = f"{(host or DEFAULT_OLLAMA_HOST).rstrip('/')}/api/generate"
    payload = {"model": model or DEFAULT_MODEL, "prompt": prompt, "stream": False}
    if fmt is not None:
        payload["format"] = fmt
    if num_predict is not None:
        payload["options"] = {"num_predict": num_predict}
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
