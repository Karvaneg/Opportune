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
from urllib.parse import urlsplit, urlunsplit

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
# ``OPPORTUNE_LLM_TIMEOUT``. Une lettre dépasse 60 s à froid, un intake d'offre réaliste
# en sortie structurée ~85 s avec ministral-3:3b (cf. [[ollama-wsl2-acces]]). Défaut 600
# (OPP-175) : l'analyse d'un CV réel atteint ~300 s (6 expériences, dogfood OPP-174) et le
# plafond ``num_predict`` de 2048 tokens à ~4 tok/s laisse un pire cas légitime ~475 s — 300
# tronquait des CV honnêtes. Le timeout est un plafond, pas une cible : il ne ralentit pas
# les appels qui finissent tôt (EOS), il élargit juste la marge avant l'échec.
DEFAULT_LLM_TIMEOUT = 600

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


# Adresses de *bind* « toutes interfaces » : valides pour un serveur qui écoute, pas comme
# cible d'un client. Ollama les accepte dans ``OLLAMA_HOST`` (convention de bind), et sous
# Windows un client qui tente de se connecter à ``0.0.0.0`` échoue. Côté client on les ramène
# donc sur la loopback correspondante.
_BIND_ALL_TO_LOOPBACK = {"0.0.0.0": "127.0.0.1", "::": "[::1]"}

# Port d'écoute par défaut d'Ollama. Une adresse de bind nue (``OLLAMA_HOST=0.0.0.0``) sous-entend
# ce port, pas le 80 implicite d'une URL HTTP : sans lui, le client taperait un endpoint mort.
_DEFAULT_OLLAMA_PORT = 11434


def ollama_url(path: str, *, host: str | None = None) -> str:
    """Compose l'URL d'un endpoint Ollama (``/api/...``) sur l'hôte configuré.

    Source unique de la normalisation hôte + chemin (défaut :data:`DEFAULT_OLLAMA_HOST`, slash
    final rogné), partagée par la génération et le provisioning (:mod:`app.ollama_provision`).
    ``path`` est toléré avec ou sans slash de tête (``api/tags`` comme ``/api/tags``).

    ``OLLAMA_HOST`` suit la convention d'Ollama : il peut arriver **sans scheme**
    (``0.0.0.0:11434``, ``localhost``) ou pointer une adresse de bind « toutes interfaces ».
    ``urllib`` exige une URL absolue → on garantit un ``http://`` et on ramène ``0.0.0.0``/``::``
    sur la loopback, sinon la connexion lève ``ValueError`` (scheme absent) ou échoue (Windows).
    Une adresse de bind **sans port** (``0.0.0.0``, ``[::]``) reçoit le port Ollama par défaut :
    sinon l'URL retomberait sur le port 80 implicite et taperait un endpoint mort.
    """
    base = (host or DEFAULT_OLLAMA_HOST).strip().rstrip("/")
    if "://" not in base:
        base = f"http://{base}"
    parts = urlsplit(base)
    # IPv6 nu (``::``) : sans crochets, ``urllib`` ne sait pas séparer hôte et port et renvoie un
    # hostname vide (≥2 ``:`` dans le netloc ⇒ forcément de l'IPv6). On réécrit en forme crochetée
    # (``[::]``), seule forme valide en URL, avant de reconnaître l'adresse de bind.
    if parts.hostname is None and parts.netloc.count(":") >= 2 and not parts.netloc.startswith("["):
        parts = urlsplit(f"{parts.scheme}://[{parts.netloc}]")
    hostname = (parts.hostname or "").lower()
    if hostname in _BIND_ALL_TO_LOOPBACK:
        loopback = _BIND_ALL_TO_LOOPBACK[hostname]
        # Pas de port explicite sur une adresse de bind ⇒ port Ollama par défaut (et non le 80
        # qu'impliquerait l'URL HTTP nue, qui ne joindrait jamais le moteur).
        port = parts.port or _DEFAULT_OLLAMA_PORT
        parts = parts._replace(netloc=f"{loopback}:{port}")
    base_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")).rstrip("/")
    return f"{base_url}/{path.lstrip('/')}"


def build_generate_request(
    prompt: str,
    *,
    model: str | None = None,
    host: str | None = None,
    fmt: object | None = None,
    num_predict: int | None = None,
    temperature: float | None = None,
):
    """Construit l'URL et la charge utile d'une génération Ollama (``/api/generate``).

    ``fmt`` (optionnel) contraint le décodage : ``"json"`` force une syntaxe JSON valide,
    un dict force un schéma JSON (clés + types), cf. « structured outputs » d'Ollama. Absent
    → aucun champ ``format`` dans la charge (génération de texte libre, comportement d'origine).

    ``num_predict`` (optionnel) borne le nombre de tokens générés via ``options.num_predict``
    d'Ollama. Absent → aucune borne (comportement d'origine).

    ``temperature`` (optionnel) règle ``options.temperature`` d'Ollama. Absent → aucun champ,
    donc le défaut du serveur (~0.8) s'applique — à proscrire pour une tâche d'**extraction**
    où ce défaut pousse le petit modèle à inventer (OPP-213) : l'intake la fixe à 0.

    Pur (aucun appel réseau), donc directement testable. Lève ``ValueError`` si le
    prompt est vide.
    """
    if not isinstance(prompt, str) or prompt.strip() == "":
        raise ValueError("Le prompt est requis")

    url = ollama_url("api/generate", host=host)
    payload = {"model": model or DEFAULT_MODEL, "prompt": prompt, "stream": False}
    if fmt is not None:
        payload["format"] = fmt
    # ``options`` regroupe les réglages Ollama : on ne l'ajoute que s'il porte au moins un
    # champ, pour préserver la charge minimale d'origine quand rien n'est précisé.
    options = {}
    if num_predict is not None:
        options["num_predict"] = num_predict
    if temperature is not None:
        options["temperature"] = temperature
    if options:
        payload["options"] = options
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
