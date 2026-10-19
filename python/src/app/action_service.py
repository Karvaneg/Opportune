"""Service des actions sensibles (V2, OPP-096).

Confirme une **intention d'exécution sortante** — candidature ou message — sous garde de
sécurité stricte : rien ne se déclenche sans **confirmation explicite** (vérifiée en amont,
côté transport) *et*, pour une candidature, sans **décision humaine ``approved``**. Un simple
statut de pré-évaluation automatique (advisory) ne suffit **jamais**.

L'idempotence est portée ici (lecture-avant-écriture) : une seconde confirmation de la même
cible et du même type renvoie l'action existante **sans en créer ni en exécuter une nouvelle**
(``already_confirmed = True``). L'exécution reste **simulée** à ce stade (cf. ``app.action``).

Concepts distincts, dépôts distincts : l'intention d'exécution n'est **pas** écrite dans la
décision. Ce service lit la décision (pour autoriser) mais persiste dans ses propres dépôts.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from app.action import SIMULATED, ApplicationAction, OutboundMessageAction
from app.action_store import (
    ApplicationActionRepository,
    OutboundMessageActionRepository,
)
from app.decision_service import APPROVED, DecisionService


class ActionNotAllowedError(Exception):
    """L'état de la décision ne permet pas l'action sensible demandée (→ 409)."""


class UnknownTargetError(Exception):
    """La cible de l'action est inconnue (→ 404)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionService:
    """Confirme candidatures et messages sortants, idempotent et sans exécution réelle."""

    def __init__(
        self,
        decisions: DecisionService,
        applications: ApplicationActionRepository,
        messages: OutboundMessageActionRepository,
        *,
        new_id: Callable[[], str] | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.decisions = decisions
        self.applications = applications
        self.messages = messages
        # Fabrique d'identifiant et horloge injectables (déterminisme en test).
        self._new_id = new_id or (lambda: uuid.uuid4().hex)
        self._now = now or _utcnow_iso

    def confirm_application(self, recommendation_id: str) -> tuple[ApplicationAction, bool]:
        """Confirme l'intention de **candidater** à une recommandation.

        Exige une décision humaine ``approved`` : ``pending`` / ``rejected`` / décision
        absente lèvent ``ActionNotAllowedError`` (→ 409). Idempotent : si une candidature
        existe déjà pour cette recommandation, la retourne avec ``already_confirmed = True``
        sans rien recréer. Retourne le couple ``(action, already_confirmed)``.
        """
        # Idempotence d'abord : une candidature déjà confirmée a été autorisée au moment de sa
        # création (``decision_status_at_confirmation`` en garde la trace d'audit). On la
        # retourne telle quelle même si la décision a depuis changé de statut — sans quoi une
        # re-soumission renverrait 409 alors que l'action sensible existe déjà.
        existing = self.applications.get_by_recommendation(recommendation_id)
        if existing is not None:
            return existing, True

        decision = self.decisions.get(recommendation_id)
        if decision is None or decision.status != APPROVED:
            raise ActionNotAllowedError(
                "une candidature exige une décision humaine 'approved'"
            )

        now = self._now()
        action = ApplicationAction(
            action_id="app_" + self._new_id(),
            recommendation_id=recommendation_id,
            candidate_id=decision.candidate_id,
            decision_status_at_confirmation=decision.status,
            confirmed_at=now,
            created_at=now,
            status=SIMULATED,
        )
        self.applications.save(action)
        return action, False

    def confirm_message(self, contact_id: str) -> tuple[OutboundMessageAction, bool]:
        """Confirme l'intention d'**envoyer un message** à une cible.

        En V2, ``contact_id`` vaut l'``recommendation_id`` : la cible est connue ssi une
        décision persistée porte cet id (sinon ``UnknownTargetError`` → 404). Contrairement à
        la candidature, aucun statut ``approved`` n'est requis (contacter n'est pas gated sur
        ``approved`` ; seule la confirmation explicite l'est, vérifiée en amont). Idempotent
        par ``contact_id``. Retourne le couple ``(action, already_confirmed)``.
        """
        decision = self.decisions.get(contact_id)
        if decision is None:
            raise UnknownTargetError(f"cible inconnue : {contact_id!r}")

        existing = self.messages.get_by_contact(contact_id)
        if existing is not None:
            return existing, True

        now = self._now()
        action = OutboundMessageAction(
            action_id="msg_" + self._new_id(),
            contact_id=contact_id,
            recommendation_id=contact_id,
            candidate_id=decision.candidate_id,
            confirmed_at=now,
            created_at=now,
            status=SIMULATED,
        )
        self.messages.save(action)
        return action, False

    def mark_applied(
        self, recommendation_id: str, applied_at: str | None = None
    ) -> tuple[ApplicationAction, bool]:
        """Déclare qu'on a **réellement candidaté** à une recommandation (suivi, OPP-xxx).

        Exige une **intention préalablement notée** (``confirm_application``) : sans elle,
        lève ``ActionNotAllowedError`` (→ 409) — on ne « candidate » pas une offre qu'on n'a
        pas d'abord décidé de viser. ``applied_at`` permet de déclarer un **jour passé** (ex.
        « candidaté il y a 15 jours ») : seule sa **date** est retenue, l'**heure** reçoit
        toujours l'instant courant (``self._now()``) — on ne demande pas d'horaire à l'humain
        mais on horodate l'enregistrement. ``None`` = aujourd'hui. Rien n'est envoyé. Idempotent
        — si la candidature est déjà marquée, la retourne avec ``already = True`` sans réécrire
        la date (pour la corriger : annuler puis re-déclarer). Retourne ``(action, already_applied)``.
        """
        existing = self.applications.get_by_recommendation(recommendation_id)
        if existing is None:
            raise ActionNotAllowedError(
                "note d'abord ton intention de candidater avant de déclarer la candidature"
            )
        if existing.applied_at is not None:
            return existing, True

        when = self._at_now_time(applied_at) if applied_at is not None else self._now()
        self.applications.set_applied(recommendation_id, when)
        return replace(existing, applied_at=when), False

    def _at_now_time(self, day: str) -> str:
        """Combine le **jour** déclaré (``day``, ISO) avec l'**heure courante** de ``self._now()``.

        L'humain choisit une date sans horaire ; on garde cette date mais on y colle l'heure
        (et le fuseau) de l'instant d'enregistrement, pour un horodatage réaliste même quand le
        jour déclaré n'est pas aujourd'hui.
        """
        now = datetime.fromisoformat(self._now())
        chosen = datetime.fromisoformat(day)
        return now.replace(year=chosen.year, month=chosen.month, day=chosen.day).isoformat()

    def unmark_applied(self, recommendation_id: str) -> ApplicationAction:
        """Annule une candidature déclarée par erreur : retour à l'état « intention notée ».

        L'intention est **conservée** (on retire seulement la date de candidature). Exige une
        intention existante (sinon ``ActionNotAllowedError`` → 409). Idempotent : annuler une
        candidature non déclarée ne change rien. Retourne l'action remise à jour.
        """
        existing = self.applications.get_by_recommendation(recommendation_id)
        if existing is None:
            raise ActionNotAllowedError("aucune candidature à annuler pour cette offre")
        if existing.applied_at is None:
            return existing
        self.applications.set_applied(recommendation_id, None)
        return replace(existing, applied_at=None)

    def get_application(self, recommendation_id: str) -> ApplicationAction | None:
        """Relit l'intention de candidater confirmée pour une recommandation, ou ``None``.

        Lecture **pure** (aucune création, aucune garde ``approved``) : sert à afficher dans
        l'UI qu'une intention a déjà été notée (et si elle a abouti à une candidature), sans
        avoir à re-POSTer. La propriété est vérifiée en amont (le détail de la reco est
        owner-gated).
        """
        return self.applications.get_by_recommendation(recommendation_id)

    def count_applied_for_candidate(self, candidate_id: str) -> int:
        """Nombre de candidatures **déclarées** (``applied``) pour un candidat (cockpit OPP-163).

        Lecture pure : la propriété est vérifiée en amont (l'endpoint stats est owner-gated).
        """
        return self.applications.count_applied(candidate_id)
