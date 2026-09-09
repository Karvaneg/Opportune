"""Autorisation des interactions Discord (V2, OPP-124).

Le **vrai contrôle de sécurité** du récepteur de clics : décider *qui* a le droit de
valider un dossier, indépendamment de la voie de réception (gateway ou endpoint signé).

La garantie d'authenticité du canal (signature en voie A, token du bot en voie B) prouve
seulement que l'interaction *vient de Discord* — pas qu'elle vient d'une **personne
autorisée**. Ce module ajoute ce second contrôle : il extrait l'identité Discord du
cliqueur du payload d'interaction, puis la confronte à une **allowlist** configurable. Un
id présent dans l'allowlist vaut le rôle ``reviewer`` de l'API (OPP-097) pour la décision ;
tout autre clic est refusé, sans qu'aucune décision ne soit enregistrée.

Pur et testable sans réseau : à partir d'un payload d'interaction simulé, on décide
autorisé/refusé sans toucher à Discord.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# Variable d'environnement portant les IDs Discord autorisés (CSV).
ENV_VAR = "DISCORD_REVIEWER_IDS"


def extract_discord_user_id(interaction: object) -> str | None:
    """Extrait l'ID Discord du cliqueur d'un payload d'interaction, ou ``None``.

    L'identité arrive sous deux formes selon le contexte : dans un **salon** (guild), le
    cliqueur est niché sous ``member.user`` ; en **message privé**, au niveau racine
    ``user``. On privilégie ``member.user`` (contexte salon, cas nominal du push-to-triage)
    puis on retombe sur ``user``. Toute forme absente ou malformée → ``None`` (jamais un id
    fabriqué), ce qui mène à un refus en amont.
    """
    if not isinstance(interaction, dict):
        return None
    member = interaction.get("member")
    if isinstance(member, dict):
        uid = _user_id(member.get("user"))
        if uid is not None:
            return uid
    return _user_id(interaction.get("user"))


def _user_id(user: object) -> str | None:
    """Retourne ``user["id"]`` s'il s'agit d'une chaîne non vide, sinon ``None``."""
    if isinstance(user, dict):
        uid = user.get("id")
        if isinstance(uid, str) and uid:
            return uid
    return None


@dataclass(frozen=True)
class ReviewerAllowlist:
    """Ensemble des IDs Discord autorisés à valider (mapping identité → rôle ``reviewer``).

    **Fail-closed** : une allowlist vide n'autorise personne. C'est le comportement sûr par
    défaut — une mauvaise configuration (variable absente ou vide) refuse tout le monde
    plutôt que d'ouvrir la validation à n'importe qui.
    """

    allowed: frozenset[str]

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, var: str = ENV_VAR) -> "ReviewerAllowlist":
        """Construit l'allowlist depuis ``env[var]`` : des IDs séparés par des virgules.

        Les espaces autour de chaque id sont ignorés et les entrées vides écartées. Variable
        absente ou vide → allowlist vide (donc fail-closed, cf. la note de classe).
        """
        raw = env.get(var, "") or ""
        return cls(frozenset(part.strip() for part in raw.split(",") if part.strip()))

    def is_allowed(self, user_id: str | None) -> bool:
        """L'``user_id`` figure-t-il dans l'allowlist ? ``None``/absent → ``False``."""
        return bool(user_id) and user_id in self.allowed
