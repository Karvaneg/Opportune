"""Récepteur live des clics Discord — adaptateur gateway (V2, OPP-125, option B).

Ferme la boucle MVP en conditions réelles : un process long se connecte à la **gateway**
Discord (connexion **sortante**, aucune URL publique, rien d'exposé sur la machine),
reçoit les clics de boutons et les route vers la décision métier déjà testée.

Découpage fidèle à l'architecture — la logique risquée est isolée du réseau :

- **partie pure/testable** (ce module, sans dépendance) : `build_decider` (le ``decide``
  réel, en process, qui mappe un verbe sur un statut et appelle
  ``HermesOrchestrator.record_human_decision``) et `process_interaction` (routage d'un
  payload d'interaction vers ``handle_interaction``, allowlist OPP-124 appliquée avant
  toute décision, jamais d'exception qui ferait tomber la boucle) ;
- **coquille I/O async** (`run_gateway` / `main`, ``pragma: no cover``) : connexion,
  heartbeat et reconnexion délégués à ``discord.py`` (dépendance confinée à l'extra
  ``[discord]``, importée **paresseusement** pour que le cœur reste importable sans elle).

Comme ``server.py`` pour l'HTTP, cet adaptateur ne porte **aucune** logique métier neuve.
"""

from __future__ import annotations

import logging
import os
from typing import Mapping

from app.discord_authz import ReviewerAllowlist
from app.discord_review import (
    DecideFn,
    InteractionError,
    handle_interaction,
)

logger = logging.getLogger("hermes.discord_gateway")

# Verbe de bouton → statut de validation humaine (miroir de _DECISION_VERBS dans api/app.py,
# source de vérité : POST /recommendations/{id}/decision, OPP-094).
_VERB_TO_STATUS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}

# Drapeau et type de réponse d'interaction (identiques à app.discord_review).
_EPHEMERAL = 64
_RESPONSE_CHANNEL_MESSAGE = 4

# Retour éphémère quand l'interaction reçue n'est pas un clic de décision exploitable :
# on répond (Discord exige un ACK) sans jamais laisser l'exception tomber la boucle.
_UNRECOGNIZED = "🤔 Interaction non reconnue."

# Retour éphémère quand la décision elle-même échoue (dossier introuvable après un reset,
# carte ancienne, erreur de persistance…) : on ACK quand même plutôt que de laisser
# l'exception remonter et priver Discord de réponse.
_FAILED = "⚠️ Décision impossible : dossier introuvable ou erreur interne."


def _ephemeral(content: str) -> dict:
    """Réponse d'interaction éphémère (ACK Discord) portant ``content``."""
    return {
        "type": _RESPONSE_CHANNEL_MESSAGE,
        "data": {"content": content, "flags": _EPHEMERAL},
    }


def build_decider(orchestrator) -> DecideFn:
    """Fabrique le ``decide`` réel (en process) branché sur l'orchestrateur Hermes.

    Retourne une fonction ``(recommendation_id, verb, comment) -> Decision`` qui traduit le
    verbe du bouton en statut de validation humaine et délègue à
    ``HermesOrchestrator.record_human_decision`` (persistée + historisée, idempotente).
    L'autorisation est déjà tranchée en amont (allowlist) : ce décideur n'applique que la
    décision. Lève ``ValueError`` sur un verbe inconnu (ne devrait pas arriver — le
    ``custom_id`` est validé au décodage).
    """

    def decide(recommendation_id: str, verb: str, comment: str | None):
        status = _VERB_TO_STATUS.get(verb)
        if status is None:
            raise ValueError(f"verbe de décision inconnu : {verb!r}")
        return orchestrator.record_human_decision(
            recommendation_id, status, comment=comment
        )

    return decide


def process_interaction(
    interaction: dict, *, decide: DecideFn, allowlist: ReviewerAllowlist
) -> dict:
    """Route un payload d'interaction vers ``handle_interaction``, **sans jamais lever**.

    Enveloppe ``handle_interaction`` (qui applique l'allowlist puis décide) en rattrapant
    toute exception : une interaction non reconnue (``InteractionError``) *ou* une décision
    qui échoue (``UnknownDecisionError`` sur une carte périmée, erreur de persistance…)
    renvoie une réponse éphémère plutôt que de faire tomber le process long et de priver
    Discord de son ACK. C'est le seam résilient du récepteur, testable sans réseau à partir
    d'un payload simulé — le pari assumé : mieux vaut un message d'erreur au cliqueur qu'une
    boucle live interrompue.
    """
    try:
        return handle_interaction(interaction, decide, allowlist=allowlist)
    except InteractionError:
        # Clic étranger/malformé : bénin et attendu, pas la peine d'alarmer les logs.
        return _ephemeral(_UNRECOGNIZED)
    except Exception:
        # Échec réel de la décision : on ACK quand même, mais on trace (traceback) pour le
        # debug — cohérent avec le logging d'app.llm_client, sinon l'erreur serait avalée.
        logger.exception("Échec du traitement d'une interaction Discord")
        return _ephemeral(_FAILED)


def build_gateway_decider(conn) -> DecideFn:
    """Assemble l'orchestrateur Hermes sur ``conn`` et en dérive le ``decide`` réel.

    Câblage isolé (touche la base, pas le réseau) pour rester testable : c'est le pont entre
    la coquille gateway et le cœur métier. Mêmes dépôts que le reste de l'app.
    """
    from app.decision_service import DecisionService
    from app.decision_store import DecisionStore
    from app.offer_store import OfferStore
    from app.profile_store import ProfileStore
    from app.recommendation_service import RecommendationService

    from hermes.orchestrator import HermesOrchestrator
    from hermes.run_store import RunStore

    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return build_decider(orchestrator)


def _interaction_payload(user_id: str, custom_id: str | None) -> dict:
    """Reconstruit le payload minimal attendu par ``process_interaction`` (contexte salon)."""
    return {"data": {"custom_id": custom_id}, "member": {"user": {"id": user_id}}}


def run_gateway(  # pragma: no cover - process long async (réseau Discord), non testé
    *, token: str, decide: DecideFn, allowlist: ReviewerAllowlist
) -> None:
    """Connecte le bot à la gateway et route chaque clic de bouton vers la décision.

    ``discord.py`` (extra ``[discord]``) gère la connexion sortante, le heartbeat et la
    reconnexion. À chaque interaction de composant, on reconstruit un payload, on le passe à
    ``process_interaction`` (allowlist + décision) et on répond en **éphémère** dans les
    délais d'ACK de Discord. Import paresseux : le module reste utilisable sans la dépendance.
    """
    import discord  # import différé : confiné à l'extra [discord]

    intents = discord.Intents.none()

    class _ReviewClient(discord.Client):
        async def on_interaction(self, interaction: "discord.Interaction") -> None:
            if interaction.type != discord.InteractionType.component:
                return
            custom_id = (interaction.data or {}).get("custom_id")
            payload = _interaction_payload(str(interaction.user.id), custom_id)
            response = process_interaction(payload, decide=decide, allowlist=allowlist)
            await interaction.response.send_message(
                response["data"]["content"], ephemeral=True
            )

    _ReviewClient(intents=intents).run(token)


def main(env: Mapping[str, str] | None = None) -> None:  # pragma: no cover - point d'entrée réseau
    """Entrée : connecte le récepteur live à Discord.

    Variables : ``DISCORD_BOT_TOKEN`` (obligatoire), ``DISCORD_REVIEWER_IDS`` (allowlist,
    obligatoire — fail-closed sinon personne ne pourrait valider), ``OPPORTUNE_DB_PATH``
    (via ``app.db.connect``). Échec net au démarrage si un requis manque.
    """
    from app.db import connect

    env = os.environ if env is None else env

    token = env.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("DISCORD_BOT_TOKEN manquant : le récepteur ne peut pas se connecter.")
    allowlist = ReviewerAllowlist.from_env(env)
    if not allowlist.allowed:
        raise SystemExit(
            "DISCORD_REVIEWER_IDS manquant : sans reviewer autorisé, aucun clic ne pourrait "
            "être validé (fail-closed)."
        )

    decide = build_gateway_decider(connect())
    run_gateway(token=token, decide=decide, allowlist=allowlist)


if __name__ == "__main__":  # pragma: no cover
    main()
