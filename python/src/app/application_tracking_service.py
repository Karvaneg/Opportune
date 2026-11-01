"""Service du suivi post-candidature (OPP-223).

Ajoute des événements de suivi (entretien, rejet, offre reçue, relance) à une candidature
**déjà déclarée** — et relit l'historique. La garde est simple : on ne suit que ce à quoi
on a déclaré avoir candidaté (``ApplicationAction.applied_at`` posé). Noter un entretien sur
une offre qu'on n'a pas postulée n'a pas de sens.

Concepts et dépôts distincts : le suivi lit la candidature (``ApplicationActionRepository``,
pour la garde et le ``candidate_id``) mais persiste dans son propre dépôt
(``ApplicationTrackingRepository``). Aucune action sortante, aucun envoi : c'est du pointage
saisi à la main, comme ``mark_applied``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.application_tracking import TrackingEvent, create_tracking_event
from app.application_tracking_store import ApplicationTrackingRepository
from app.action_store import ApplicationActionRepository


class TrackingNotAllowedError(Exception):
    """Le suivi n'est pas permis dans l'état courant de la candidature (→ 409)."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApplicationTrackingService:
    """Ajoute et relit les événements de suivi d'une candidature déclarée."""

    def __init__(
        self,
        applications: ApplicationActionRepository,
        tracking: ApplicationTrackingRepository,
        *,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.applications = applications
        self.tracking = tracking
        self._now = now or _utcnow_iso

    def add_event(
        self,
        recommendation_id: str,
        kind: str,
        *,
        event_date: str | None = None,
        comment: str | None = None,
    ) -> TrackingEvent:
        """Ajoute un événement de suivi à une candidature déclarée.

        Un ``kind`` inconnu (ou une ``event_date`` sur autre chose qu'un entretien) lève
        ``TrackingError`` (→ 400, porté par le domaine) ; la validation de forme précède la garde
        d'état, pour qu'une payload invalide reste un 400 même sur une candidature non déclarée.
        Exige ensuite une candidature **déclarée candidatée** (``applied_at`` posé) : sans elle,
        lève ``TrackingNotAllowedError`` (→ 409). ``event_date`` date un entretien prévu (souvent
        futur), ``comment`` est libre. Retourne l'événement créé.
        """
        event = create_tracking_event(
            kind, event_date=event_date, comment=comment, now=self._now
        )

        application = self.applications.get_by_recommendation(recommendation_id)
        if application is None or application.applied_at is None:
            raise TrackingNotAllowedError(
                "le suivi n'est possible que pour une offre déclarée candidatée"
            )

        self.tracking.append(recommendation_id, application.candidate_id, event)
        return event

    def history(self, recommendation_id: str) -> tuple[TrackingEvent, ...]:
        """Relit l'historique de suivi d'une candidature (lecture pure, ordre chronologique).

        La propriété est vérifiée en amont (le détail de la reco est owner-gated).
        """
        return self.tracking.history(recommendation_id)

    def history_for(
        self, recommendation_ids: list[str]
    ) -> dict[str, tuple[TrackingEvent, ...]]:
        """Historique de suivi de plusieurs candidatures (lecture en lot, flux d'activité).

        Délègue au dépôt (un seul SELECT) : le cockpit agrège le journal transversal sans un
        accès par recommandation.
        """
        return self.tracking.events_for(recommendation_ids)
