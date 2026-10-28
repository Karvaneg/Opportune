"""Localisation et résolution des assets du front compilé (OPP-191).

En mode packagé (OPP-190), l'API ne se contente pas de servir du JSON : elle sert
aussi le **front compilé** (``frontend/dist``) en statique, pour qu'un binaire
unique soit l'application complète sur ``localhost`` — sans Node ni serveur Vite.
Les appels de données restent préfixés ``/api`` (routés vers le dispatcher) ; tout
le reste relève du front.

Trois responsabilités, toutes testables :

- ``frontend_dist_dir`` : *où* est le ``dist`` selon le contexte (binaire gelé,
  override, dev) ;
- ``resolve_static_file`` : *quel* fichier servir pour une URL — avec fallback SPA
  (une route client comme ``/runs/42`` renvoie ``index.html``) et garde
  anti-traversée de chemin ;
- ``content_type_for`` : *avec quel* content-type servir un fichier.
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import unquote

# Content-types forcés pour les extensions servies par Vite, **avant** ``mimetypes`` (OPP-191).
# ``mimetypes`` lit le registre Windows, où ``.js`` peut être mappé sur ``text/plain`` : un
# module ES (``<script type="module">``) servi en ``text/plain`` est alors **refusé** par le
# navigateur (contrôle MIME strict) → app blanche. On fige donc les types critiques du bundle.
_FORCED_CONTENT_TYPES = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".wasm": "application/wasm",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def frontend_dist_dir() -> Path | None:
    """Répertoire du front compilé, ou ``None`` si introuvable (dev sans build).

    Priorités : ``OPPORTUNE_FRONTEND_DIST`` (override) ; binaire gelé → dossier
    embarqué dans le bundle PyInstaller ; dev → ``frontend/dist`` à la racine du
    dépôt s'il a été construit (sinon ``None`` : c'est Vite qui sert en dev).
    """
    override = os.environ.get("OPPORTUNE_FRONTEND_DIST")
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    if getattr(sys, "frozen", False):
        bundled = Path(sys._MEIPASS) / "frontend_dist"  # type: ignore[attr-defined]
        return bundled if bundled.is_dir() else None
    # src/api/frontend_assets.py → parents[3] = racine du dépôt.
    repo_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    return repo_dist if repo_dist.is_dir() else None


def resolve_static_file(dist_dir: Path, url_path: str) -> Path | None:
    """Fichier à servir pour une requête GET (hors ``/api``), ou ``None`` si 404.

    - un fichier réel du ``dist`` (``/assets/x.js``, ``/favicon.svg``) est servi tel quel ;
    - une **route client** sans extension (``/``, ``/runs/42``) retombe sur ``index.html``
      (fallback SPA : React Router prend le relais côté navigateur) ;
    - un asset **avec extension mais absent** (``/assets/vieux.js``) → ``None`` (vrai 404,
      on ne renvoie pas du HTML à la place d'un JS attendu) ;
    - toute tentative de sortir du ``dist`` (``../``) → ``None``.
    """
    index = dist_dir / "index.html"
    relative = unquote(url_path.split("?", 1)[0]).lstrip("/")

    if relative == "":
        return index if index.is_file() else None

    root = dist_dir.resolve()
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        return None  # traversée de chemin : refus net, pas de fallback SPA

    if candidate.is_file():
        return candidate

    # Absent : extension présente → asset manquant (404) ; sinon route client → SPA.
    if Path(relative).suffix:
        return None
    return index if index.is_file() else None


def content_type_for(filename: str) -> str:
    """Content-type à servir pour ``filename`` (fallback ``application/octet-stream``).

    Les extensions critiques du bundle Vite sont figées (cf. ``_FORCED_CONTENT_TYPES``) pour ne
    pas dépendre du registre Windows via ``mimetypes`` ; le reste passe par ``mimetypes``.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in _FORCED_CONTENT_TYPES:
        return _FORCED_CONTENT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"
