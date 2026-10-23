"""Identité locale de l'API Hermes (V2, OPP-181).

Opportune est une application **locale et mono-utilisateur** : le serveur tourne sur
``localhost`` pour une seule personne. Exiger un secret ``Bearer`` (OPP-097/098) était une
friction inutile → supprimé (direction *local-first*, OPP-181). L'authentification se réduit
donc à une **identité locale** : toute requête est servie comme l'unique utilisateur,
propriétaire de ses candidats.

On conserve néanmoins l'abstraction injectable : le métier ne dépend que de
``authenticate(headers) -> User | None``, si bien qu'un futur fournisseur (périmètre dérivé de
la base, OPP-183) pourra remplacer ``LocalAuthProvider`` sans toucher aux handlers.
L'**autorisation** (propriété d'une ressource, rôle ``reviewer``) vit toujours dans les
handlers, qui résolvent le propriétaire depuis la ressource persistée ; elle n'accorde jamais
confiance à un identifiant fourni dans le corps. Le périmètre (``owned_candidates``) reste figé
au boot pour l'instant — sa dérivation dynamique depuis la base est l'objet d'OPP-183.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    chaque requête est servie comme ``user``. Conserve le contrat ``authenticate(headers)`` pour
    rester interchangeable avec un futur fournisseur (OPP-183) sans toucher aux handlers.
    """

    def __init__(self, user: User) -> None:
        self._user = user

    def authenticate(self, headers: dict | None = None) -> User:  # noqa: ARG002 - en-têtes ignorés en local
        return self._user
