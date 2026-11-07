"""Contrôle de l'en-tête ``Host`` sur toutes les requêtes (OPP-233, anti DNS rebinding).

Le contrôle d'``Origin`` (``origin_guard``) ne couvre pas le DNS rebinding : une page servie
sur ``http://evil.example:8000`` fait repointer son domaine vers ``127.0.0.1``. Ses requêtes
deviennent alors « même site » pour le navigateur, qui la laisse **lire** toutes les réponses
de l'API (profil, lettres, réglages) et y écrire avec une ``Origin`` qu'on ne peut pas refuser
sans refuser aussi le vrai front.

Dans ce cas, le navigateur envoie ``Host: evil.example:8000``. L'API n'est jointe légitimement
que par un nom local (``127.0.0.1``, ``localhost``, ``[::1]``) sur son port d'écoute : la webview
Tauri, le navigateur sur le front packagé, et le proxy Vite, qui réécrit ``Host`` vers sa cible
(``changeOrigin``). Tout autre ``Host`` est refusé.

Une requête **sans** ``Host`` (HTTP/1.0, client hors navigateur) est acceptée : un navigateur
l'envoie toujours.
"""

from __future__ import annotations

from api.origin_guard import LOOPBACK_HOSTS


def allowed_hosts(api_port: int) -> frozenset[str]:
    """Valeurs d'``Host`` acceptées quand l'API écoute sur ``api_port``."""
    return frozenset(f"{host}:{api_port}" for host in LOOPBACK_HOSTS)


def is_host_allowed(host: str | None, allowed: frozenset[str]) -> bool:
    """La requête portant cet en-tête ``Host`` est-elle acceptée ? (casse ignorée)"""
    if host is None:
        return True
    return host.strip().lower() in allowed
