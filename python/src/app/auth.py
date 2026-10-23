"""Identité locale de l'API Hermes (V2, OPP-181).

Opportune est une application **locale et mono-utilisateur** : le serveur tourne sur
``localhost`` pour une seule personne. Exiger un secret ``Bearer`` (OPP-097/098) était une
friction inutile → supprimé (direction *local-first*, OPP-181). L'authentification se réduit
donc à une **identité locale** : toute requête est servie comme l'unique utilisateur,
propriétaire de ses candidats.

On conserve néanmoins l'abstraction injectable : le métier ne dépend que de
``authenticate(headers) -> User | None``, si bien que le fournisseur de périmètre peut évoluer
sans toucher aux handlers. L'**autorisation** (propriété d'une ressource, rôle ``reviewer``) vit
toujours dans les handlers, qui résolvent le propriétaire depuis la ressource persistée ; elle
n'accorde jamais confiance à un identifiant fourni dans le corps. Le périmètre
(``owned_candidates``) est désormais **dérivé dynamiquement de la base** à chaque requête
(OPP-183) via un ``owned_provider`` adossé au ``CandidateRegistry`` — cf. ``LocalAuthProvider``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

# Seul rôle distinct en V2 : requis pour la validation humaine et les actions sensibles.
REVIEWER = "reviewer"


@dataclass(frozen=True)
class User:
    """Identité : son id, son rôle et les candidats qu'elle possède."""

    id: str
    role: str
    owned_candidates: frozenset[str]

    def owns(self, candidate_id: str) -> bool:
        """L'utilisateur a-t-il ce candidat dans son périmètre ?"""
        return candidate_id in self.owned_candidates

    @property
    def is_reviewer(self) -> bool:
        """Détient-il le rôle ``reviewer`` (validation humaine / actions sensibles) ?"""
        return self.role == REVIEWER


class LocalAuthProvider:
    """Authentifie **toute** requête comme l'unique utilisateur local — sans jeton.

    En local mono-utilisateur il n'y a aucun secret à vérifier : les en-têtes sont ignorés et
    chaque requête est servie comme l'utilisateur local.

    Périmètre **dynamique** (OPP-183) : si un ``owned_provider`` est fourni, le périmètre
    (``owned_candidates``) est **recalculé à chaque requête** depuis la base (registre des
    candidats), au lieu d'être figé au boot. Sans provider, l'utilisateur est servi tel quel —
    pratique pour les tests, qui fixent un périmètre statique. Le provider est rappelé à chaque
    ``authenticate`` pour que l'ajout/suppression d'un candidat soit pris en compte sans
    redémarrage ; l'instantané reste cohérent le temps d'une requête (serveur séquentiel).
    """

    def __init__(
        self,
        user: User,
        *,
        owned_provider: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self._user = user
        self._owned_provider = owned_provider

    def authenticate(self, headers: dict | None = None) -> User:  # noqa: ARG002 - en-têtes ignorés en local
        if self._owned_provider is None:
            return self._user
        return replace(self._user, owned_candidates=frozenset(self._owned_provider()))
