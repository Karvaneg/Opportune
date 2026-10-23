"""Routeur d'espace : aiguille chaque requête vers l'API « Mon espace » ou « Démo » (OPP-182).

Opportune est local-first (OPP-181) ; OPP-182 ajoute un **écran d'accueil** qui laisse choisir entre
ses vraies données (« Mon espace ») et un **exemple isolé** (« Démo »). Les deux espaces sont deux
bases SQLite **distinctes** — jamais mélangées. Plutôt que de relancer le serveur sur l'autre base,
on assemble **deux** :class:`~api.app.HermesApi` au boot (une par base) et ce routeur choisit la cible
par requête, selon l'en-tête ``X-Opportune-Space`` posé par le front.

Transport-agnostique comme ``HermesApi`` : il expose la **même** méthode :meth:`dispatch`, donc
``api.server.make_handler`` l'utilise sans rien changer (duck typing). En-tête absent ou inconnu →
« Mon espace » : jamais la démo par accident (défaut sûr, on ne bascule sur l'exemple que sur demande
explicite du front).
"""

from __future__ import annotations

from collections.abc import Callable

from api.app import HermesApi, Response

# Nom de l'en-tête HTTP qui porte l'espace choisi, et valeurs reconnues.
SPACE_HEADER = "X-Opportune-Space"
SPACE_MINE = "mine"
SPACE_DEMO = "demo"


class SpaceRouter:
    """Aiguille ``dispatch`` vers l'API de l'espace demandé (``X-Opportune-Space``).

    ``mine`` sert les vraies données, ``demo`` l'exemple isolé (base séparée). Le routeur ne
    connaît rien du métier : il lit l'en-tête (insensible à la casse, comme l'auth en aval),
    choisit l'API puis délègue. Valeur absente/inconnue → ``mine`` (défaut sûr).

    Il porte aussi les **commandes d'espace démo** (OPP-182) — ``POST /demo/reset`` (vider) et
    ``POST /demo/restore`` (restaurer la vitrine). Elles sont interceptées **avant** le routage
    et agissent toujours sur la base démo, quel que soit l'en-tête : impossible, par
    construction, de viser la base réelle. Absentes (déploiement sans démo) → routées comme le
    reste, donc 404.
    """

    def __init__(
        self,
        *,
        mine: HermesApi,
        demo: HermesApi,
        demo_commands: dict[str, Callable[[], Response]] | None = None,
    ) -> None:
        self._apis = {SPACE_MINE: mine, SPACE_DEMO: demo}
        self._demo_commands = demo_commands or {}

    def dispatch(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> Response:
        path_only = path.partition("?")[0]
        if method.upper() == "POST":
            command = self._demo_commands.get(path_only)
            if command is not None:
                return command()
        space = self._resolve_space(headers or {})
        return self._apis[space].dispatch(method, path, body, headers)

    def _resolve_space(self, headers: dict) -> str:
        """Lit ``X-Opportune-Space`` (casse ignorée) ; ``mine`` si absent ou non reconnu."""
        wanted = SPACE_HEADER.lower()
        for key, value in headers.items():
            if key.lower() == wanted:
                candidate = (value or "").strip().lower()
                return candidate if candidate in self._apis else SPACE_MINE
        return SPACE_MINE
