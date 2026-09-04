"""Authentification et identité de l'API Hermes (V2, OPP-097).

Abstraction **minimale** et injectable : un ``AuthProvider`` résout une requête (ses
en-têtes) en un ``User`` identifié, ou ``None`` si l'authentification échoue. Le métier ne
dépend que de cette interface — un vrai fournisseur (JWT, session, OIDC) pourra la remplacer
sans toucher aux handlers.

MVP : jetons **Bearer** statiques ``token -> User`` injectés. La comparaison du secret est
faite en **temps constant** (``hmac.compare_digest``) pour ne pas fuiter le jeton par timing.
Un jeton absent, d'un schéma autre que ``Bearer``, ou inconnu (invalide/expiré) → ``None``
(→ 401 côté transport). L'``autorisation`` (propriété d'une ressource, rôle) n'est **pas**
ici : elle vit dans les handlers, qui résolvent le propriétaire depuis la ressource persistée
et n'accordent jamais confiance à un identifiant fourni dans le corps.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass

# Seul rôle distinct en V2 : requis pour la validation humaine et les actions sensibles.
REVIEWER = "reviewer"


@dataclass(frozen=True)
class User:
    """Identité authentifiée : son id, son rôle et les candidats qu'elle possède."""

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


class AuthProvider:
    """Authentifie une requête par jeton ``Authorization: Bearer <token>`` (temps constant)."""

    def __init__(self, tokens: dict[str, User]) -> None:
        # Copie défensive : la table de jetons n'est pas mutée de l'extérieur après coup.
        self._tokens = dict(tokens)

    def authenticate(self, headers: dict) -> User | None:
        """Retourne l'utilisateur du jeton porté par ``headers``, ou ``None`` si invalide.

        ``None`` couvre indistinctement : en-tête absent, schéma non-``Bearer``, jeton vide,
        ou jeton inconnu (invalide/expiré) — tous mènent à un 401 côté transport.
        """
        token = self._bearer_token(headers)
        if token is None:
            return None
        # Comparaison en temps constant contre chaque jeton connu (pas de court-circuit qui
        # fuiterait la présence d'un préfixe valide).
        for known, user in self._tokens.items():
            if hmac.compare_digest(known, token):
                return user
        return None

    @staticmethod
    def _bearer_token(headers: dict) -> str | None:
        """Extrait le jeton d'un en-tête ``Authorization: Bearer <token>`` (clé insensible à la casse)."""
        value = None
        for key, raw in (headers or {}).items():
            if key.lower() == "authorization":
                value = raw
                break
        if not value:
            return None
        parts = value.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        token = parts[1].strip()
        return token or None
