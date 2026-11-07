"""Contrôle de l'en-tête ``Origin`` sur les écritures (OPP-233).

L'API écoute sur ``localhost`` sans login ni jeton (ADR 0003). Sans ce contrôle, n'importe
quelle page web ouverte dans le navigateur pourrait envoyer un POST à l'API locale : le
navigateur l'empêche de **lire** la réponse, mais pas d'**exécuter** la requête (import qui
remplace un espace, suppression, collecte…).

Un navigateur joint toujours l'en-tête ``Origin`` à une écriture venant d'une page. On accepte :

- l'origine de l'API elle-même (front servi par l'API, webview Tauri) : ``127.0.0.1``,
  ``localhost`` ou ``[::1]`` sur le port d'écoute ;
- **hors app packagée seulement**, les origines du front de dev (Vite) : mêmes hôtes sur les
  ports 5173 (``npm run dev``) et 4173 (``npm run preview``). Dans l'app packagée, aucun Vite
  d'Opportune ne tourne : une page servie sur ces ports serait celle d'une autre application ;
- les origines ajoutées par l'utilisateur dans ``OPPORTUNE_EXTRA_ORIGINS`` (liste séparée par
  des virgules), pour un front de dev ouvert depuis une autre adresse (``npm run dev -- --host``
  ouvert par l'IP WSL, par exemple).

Une requête **sans** ``Origin`` ne vient pas d'une page web (curl, tests, scripts locaux) : elle
est acceptée. Tout le reste, y compris ``Origin: null`` (iframe isolée, fichier local), est refusé.
"""

from __future__ import annotations

from typing import Iterable, Mapping

# Ports du front de dev : serveur Vite (``npm run dev``) et prévisualisation du build
# (``npm run preview``). Leur proxy ``/api`` transmet ``Origin`` tel quel.
DEV_FRONT_PORTS = (5173, 4173)

# Noms de la machine locale, tels qu'un navigateur les écrit dans ``Origin`` et ``Host``.
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")

EXTRA_ORIGINS_ENV = "OPPORTUNE_EXTRA_ORIGINS"


def _normalize(origin: str) -> str:
    """Forme comparable d'une origine : sans espaces, sans ``/`` final, en minuscules."""
    return origin.strip().rstrip("/").lower()


def parse_extra_origins(env: Mapping[str, str]) -> tuple[str, ...]:
    """Origines supplémentaires lues dans ``OPPORTUNE_EXTRA_ORIGINS`` (virgules), normalisées."""
    raw = env.get(EXTRA_ORIGINS_ENV, "")
    return tuple(_normalize(item) for item in raw.split(",") if item.strip())


def allowed_origins(
    api_port: int, *, allow_dev_front: bool, extra: Iterable[str] = ()
) -> frozenset[str]:
    """Origines autorisées à écrire quand l'API écoute sur ``api_port``.

    ``allow_dev_front`` : accepter aussi les ports du front de dev (faux dans l'app packagée).
    """
    ports = {api_port, *DEV_FRONT_PORTS} if allow_dev_front else {api_port}
    local = {f"http://{host}:{port}" for host in LOOPBACK_HOSTS for port in ports}
    return frozenset(local | {_normalize(origin) for origin in extra})


def is_write_allowed(origin: str | None, allowed: frozenset[str]) -> bool:
    """L'écriture portant cet en-tête ``Origin`` est-elle acceptée ?

    ``origin`` vaut ``None`` quand l'en-tête est absent (client hors navigateur) : accepté.
    La comparaison ignore la casse et un ``/`` final, que certains clients ajoutent.
    """
    if origin is None:
        return True
    return _normalize(origin) in allowed
