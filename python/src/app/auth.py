"""Authentification et identité de l'API Hermes (V2, OPP-097).

Abstraction **minimale** et injectable : un ``AuthProvider`` résout une requête (ses
en-têtes) en un ``User`` identifié, ou ``None`` si l'authentification échoue. Le métier ne
dépend que de cette interface — un vrai fournisseur (JWT, session, OIDC) pourra la remplacer
sans toucher aux handlers.

MVP : jetons **Bearer** injectés, chacun un ``User`` nu (sans expiration) ou un
``TokenRecord`` porteur d'une **échéance** (``expires_at``, OPP-098). La comparaison du secret
est faite en **temps constant** (``hmac.compare_digest``) pour ne pas fuiter le jeton par
timing, et l'échéance est évaluée via une **horloge injectable** (déterminisme en test),
comparée en UTC. Un jeton absent, d'un schéma autre que ``Bearer``, inconnu, **expiré**, ou
dont l'échéance est d'un format invalide → ``None`` (→ 401 côté transport), sans
révéler lequel. L'``autorisation`` (propriété d'une ressource, rôle) n'est **pas** ici : elle
vit dans les handlers, qui résolvent le propriétaire depuis la ressource persistée et
n'accordent jamais confiance à un identifiant fourni dans le corps.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

# Seul rôle distinct en V2 : requis pour la validation humaine et les actions sensibles.
REVIEWER = "reviewer"


def _utcnow() -> datetime:
    """Horloge par défaut : instant courant en UTC (aware)."""
    return datetime.now(timezone.utc)


def _to_utc(moment: datetime) -> datetime:
    """Normalise un ``datetime`` en UTC ; un instant *naïf* (sans fuseau) est présumé UTC."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _parse_iso_utc(value: object) -> datetime | None:
    """Parse une chaîne ISO 8601 en ``datetime`` **normalisé UTC**, ou ``None`` si invalide.

    Un format non-``str`` ou non-parsable → ``None`` (le jeton sera traité comme invalide,
    jamais comme valide par défaut). Un instant *naïf* (sans fuseau) est présumé UTC. Le
    suffixe ``Z`` est accepté (``fromisoformat`` ne le gère pas avant Python 3.11).
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _to_utc(parsed)


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


@dataclass(frozen=True)
class TokenRecord:
    """Jeton avec **échéance** optionnelle (OPP-098).

    ``expires_at`` (ISO 8601, comparé en UTC) borne la validité : le jeton est valide tant
    que ``now < expires_at`` (échéance **exclusive**). ``None`` = pas d'expiration (valable
    indéfiniment) — équivaut à fournir un ``User`` nu.
    """

    user: User
    expires_at: str | None = None


class AuthProvider:
    """Authentifie une requête par jeton ``Authorization: Bearer <token>`` (temps constant)."""

    def __init__(
        self,
        tokens: dict[str, User | TokenRecord],
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        # Copie défensive + normalisation : un ``User`` nu devient un ``TokenRecord`` sans
        # échéance (rétro-compat avec ``AuthProvider({token: User})``).
        self._tokens: dict[str, TokenRecord] = {
            token: value if isinstance(value, TokenRecord) else TokenRecord(value)
            for token, value in tokens.items()
        }
        # Horloge injectable (déterminisme en test) ; défaut = horloge UTC.
        self._now = now or _utcnow

    def authenticate(self, headers: dict) -> User | None:
        """Retourne l'utilisateur du jeton porté par ``headers``, ou ``None`` si invalide.

        ``None`` couvre indistinctement : en-tête absent, schéma non-``Bearer``, jeton vide,
        jeton inconnu, ou jeton **expiré** — tous mènent à un 401 côté transport, sans
        révéler lequel. Un ``expires_at`` au format invalide est traité comme un jeton
        invalide (jamais valide par défaut).
        """
        token = self._bearer_token(headers)
        if token is None:
            return None
        # Comparaison en temps constant contre chaque jeton connu (pas de court-circuit qui
        # fuiterait la présence d'un préfixe valide).
        record = None
        for known, candidate in self._tokens.items():
            if hmac.compare_digest(known, token):
                record = candidate
                break
        if record is None:
            return None
        if self._is_expired(record):
            return None
        return record.user

    def _is_expired(self, record: TokenRecord) -> bool:
        """Vrai si l'échéance est atteinte (``now >= expires_at``) ou indéterminable.

        Échéance **exclusive** : à ``now == expires_at``, le jeton est expiré. Une échéance
        au format invalide (non-parsable) est considérée expirée — on ne valide jamais un
        jeton dont on ne peut pas établir la fraîcheur.
        """
        if record.expires_at is None:
            return False  # pas d'échéance → jamais expiré
        expires_at = _parse_iso_utc(record.expires_at)
        if expires_at is None:
            return True  # échéance au format invalide → jeton invalide (401)
        return _to_utc(self._now()) >= expires_at

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
