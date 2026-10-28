"""Provisioning du modèle local via Ollama (OPP-193).

Au premier lancement, l'app doit s'assurer qu'Ollama est joignable et que le modèle
(``ministral-3:3b``) est présent, en le téléchargeant sinon — avec une **barre de
progression**. Ce module parle à l'API HTTP d'Ollama (``/api/tags`` pour l'inventaire,
``/api/pull`` qui *stream* l'avancement du téléchargement), sans dépendance externe
(``urllib``, transport injectable comme :mod:`app.llm`).

Le découpage isole la partie **pure et testable** (agrégation de la progression du stream)
de l'entrée/sortie réseau :

- :class:`PullAggregator` — à partir des lignes NDJSON d'``/api/pull``, calcule une
  fraction d'avancement et un libellé ; pur, testable sans réseau ;
- :func:`list_models` / :func:`model_present` — inventaire via ``/api/tags`` ;
- :func:`pull_model` — télécharge en poussant la progression dans un callback.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Callable

from app.llm import DEFAULT_MODEL, DEFAULT_OLLAMA_HOST

# Transport de requête simple (GET → dict), injectable pour tester sans réseau.
JsonTransport = Callable[[str], dict]
# Transport de stream (POST → itérateur de dicts, un par ligne NDJSON), injectable aussi.
StreamTransport = Callable[[str, dict], Iterator[dict]]
# Callback d'avancement du pull, appelé à chaque ligne du stream.
ProgressCallback = Callable[["PullProgress"], None]


class OllamaUnreachable(Exception):
    """Ollama n'a pas répondu (serveur absent/arrêté) — distinct d'un échec de pull."""


@dataclass(frozen=True)
class PullProgress:
    """Instantané d'avancement d'un téléchargement : libellé, fraction [0, 1], fin, erreur."""

    status: str
    fraction: float
    done: bool = False
    error: str | None = None


class PullAggregator:
    """Agrège les lignes NDJSON d'``/api/pull`` en une fraction d'avancement globale.

    Ollama télécharge plusieurs **couches** (``digest``), chacune annoncée par des lignes
    ``{"status": "pulling <digest>", "total": N, "completed": M}``. La fraction globale est
    ``somme(completed) / somme(total)`` sur toutes les couches vues (la couche des poids, ~3 Go,
    domine). Les lignes sans octets (``pulling manifest``, ``verifying``, ``success``) ne font
    qu'actualiser le libellé. ``success`` marque la fin à 100 %. Pur : aucun effet de bord.
    """

    def __init__(self) -> None:
        self._totals: dict[str, int] = {}
        self._completed: dict[str, int] = {}

    def update(self, event: dict) -> PullProgress:
        """Intègre une ligne du stream et rend l'avancement courant."""
        status = str(event.get("status", ""))

        if "error" in event:
            return PullProgress(status or "erreur", self._fraction(), error=str(event["error"]))

        digest = event.get("digest")
        total = event.get("total")
        if digest and isinstance(total, int) and total > 0:
            self._totals[digest] = total
            completed = event.get("completed")
            self._completed[digest] = int(completed) if isinstance(completed, int) else 0

        if status == "success":
            # Fin : on force 100 % même si aucune couche n'a été téléchargée (modèle déjà présent,
            # vérification seule) — le stream se termine sans forcément repasser à completed==total.
            return PullProgress("success", 1.0, done=True)

        return PullProgress(status, self._fraction())

    def _fraction(self) -> float:
        total = sum(self._totals.values())
        if total <= 0:
            return 0.0
        completed = sum(min(self._completed.get(d, 0), t) for d, t in self._totals.items())
        return completed / total


def list_models(*, host: str | None = None, transport: JsonTransport | None = None) -> list[str]:
    """Noms des modèles présents dans Ollama (``/api/tags``). Lève :class:`OllamaUnreachable`."""
    url = f"{(host or DEFAULT_OLLAMA_HOST).rstrip('/')}/api/tags"
    send = transport or _get_json
    body = send(url)
    return [m["name"] for m in body.get("models", []) if isinstance(m, dict) and "name" in m]


def model_present(
    model: str | None = None,
    *,
    host: str | None = None,
    transport: JsonTransport | None = None,
) -> bool:
    """Vrai si ``model`` (défaut :data:`app.llm.DEFAULT_MODEL`) est déjà installé dans Ollama."""
    target = model or DEFAULT_MODEL
    return target in list_models(host=host, transport=transport)


def pull_model(
    model: str | None = None,
    *,
    host: str | None = None,
    on_progress: ProgressCallback | None = None,
    transport: StreamTransport | None = None,
) -> PullProgress:
    """Télécharge ``model`` via ``/api/pull`` en poussant l'avancement dans ``on_progress``.

    Rend le dernier :class:`PullProgress` (``done=True`` si ``success``). Un stream qui se
    termine sans ``success`` rend un progrès porteur d'``error``.
    """
    target = model or DEFAULT_MODEL
    url = f"{(host or DEFAULT_OLLAMA_HOST).rstrip('/')}/api/pull"
    stream = transport or _post_stream
    aggregator = PullAggregator()
    last = PullProgress("pulling manifest", 0.0)
    for event in stream(url, {"model": target, "stream": True}):
        last = aggregator.update(event)
        if on_progress is not None:
            on_progress(last)
        if last.error is not None:
            return last
    if not last.done:
        return PullProgress(last.status, last.fraction, error="stream interrompu avant 'success'")
    return last


def _get_json(url: str, *, timeout: int = 10) -> dict:
    """GET JSON par défaut (``urllib``). Mappe une erreur réseau vers :class:`OllamaUnreachable`."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 (URL interne)
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaUnreachable(str(exc)) from exc


def _post_stream(url: str, payload: dict, *, timeout: int = 3600) -> Iterator[dict]:
    """POST JSON et itère les lignes NDJSON de la réponse (``/api/pull``). Timeout large (download)."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            for raw in response:
                line = raw.decode("utf-8").strip()
                if line:
                    yield json.loads(line)
    except urllib.error.URLError as exc:
        raise OllamaUnreachable(str(exc)) from exc
