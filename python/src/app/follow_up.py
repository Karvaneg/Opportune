"""Rappels de relance des candidatures (OPP-235).

Une candidature envoyée appelle **une relance par délai réglé** (2 par défaut après une
candidature, 3 après un entretien), comptées depuis un **point de départ** :

- la date de la candidature (délais par défaut : 5 et 8 jours) ;
- la date du **dernier entretien passé**, s'il y en a un (délais par défaut : 5, 8 et 15 jours).
  Un nouvel entretien remet donc le compteur à zéro.

Tant qu'aucune relance n'est notée (``NO_RESPONSE``, « Sans réponse / relance »), chaque délai
atteint est une relance : J+5 donne la 1re, J+8 la 2e, J+15 (après un entretien) la 3e. Une
relance notée **solde la relance due ce jour-là** : notée à J+9 (2e due), elle compte pour la 2e,
pas pour la 1re. La suivante est due **le dernier délai réglé** après la dernière relance notée
(8 jours après une candidature, 15 après un entretien). Quand la dernière relance prévue est
soldée, plus de rappel.

Une relance notée le jour même d'un entretien compte pour la candidature, pas pour l'entretien :
les relances post-entretien ne comptent qu'à partir du lendemain.

Sortent aussi de la liste : une candidature refusée par le recruteur (``REJECTED``) ou avec une
offre reçue (``OFFER``), et une candidature dont un entretien est encore à venir (on attend
l'entretien avant de relancer). Un entretien prévu aujourd'hui est « à venir », comme dans les
compteurs du cockpit (``count_upcoming_interviews``).

``next_follow_up`` annonce la prochaine relance pas encore due (fiche d'une offre), seulement
quand aucune n'est due : tant qu'une relance attend d'être notée, la date de la suivante dépend
du jour où elle le sera.

Logique pure : les dates du jour et les historiques sont fournis par l'appelant.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.application_tracking import INTERVIEW, NO_RESPONSE, OFFER, REJECTED, TrackingEvent
from app.candidate_stats import count_upcoming_interviews

# Délais par défaut, en jours depuis le point de départ.
DEFAULT_AFTER_APPLICATION = (5, 8)
DEFAULT_AFTER_INTERVIEW = (5, 8, 15)

# Point de départ des relances (clés stables, partagées avec le front).
SINCE_APPLICATION = "candidature"
SINCE_INTERVIEW = "entretien"


@dataclass(frozen=True)
class FollowUpSchedule:
    """Délais des relances, en jours depuis le point de départ, croissants : un délai = une relance.

    Le dernier délai sert aussi d'écart entre une relance notée et la suivante.
    """

    after_application: tuple[int, ...] = DEFAULT_AFTER_APPLICATION
    after_interview: tuple[int, ...] = DEFAULT_AFTER_INTERVIEW


@dataclass(frozen=True)
class FollowUpDue:
    """Une relance à faire : laquelle, depuis quel point de départ, et depuis quand elle est due."""

    since: str  # SINCE_APPLICATION | SINCE_INTERVIEW
    start_date: date
    due_date: date  # date à laquelle la relance est devenue due
    step: int  # numéro de la relance à faire (1 = première)
    total: int  # nombre de relances prévues depuis ce point de départ (= nombre de délais)


def _to_date(iso: str) -> date | None:
    """Date d'un horodatage ou d'une date ISO 8601 ; ``None`` si illisible.

    Un horodatage avec fuseau (``at``, ``applied_at``, stockés en UTC) est ramené à l'heure
    locale de la machine avant d'en prendre la date : une candidature envoyée à 00h30 en France
    compte pour ce jour-là, pas pour la veille en UTC. Une date seule (``event_date``) est gardée
    telle quelle.
    """
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.date()


def _interview_date(event: TrackingEvent) -> date | None:
    """Date de l'entretien : sa date prévue si lisible, sinon la date où il a été noté."""
    planned = _to_date(event.event_date) if event.event_date else None
    return planned or _to_date(event.at)


@dataclass(frozen=True)
class _Context:
    """Ce qui fixe le calendrier des relances d'une candidature, à une date donnée."""

    since: str
    start: date
    delays: tuple[int, ...]
    done: int  # relances soldées par les relances notées
    last_noted: date | None  # dernière relance notée qui compte


def _context(
    applied_at: str, events: Sequence[TrackingEvent], schedule: FollowUpSchedule, today: date
) -> _Context | None:
    """Point de départ, délais et relances notées ; ``None`` si plus aucune relance n'a lieu."""
    start = _to_date(applied_at)
    if start is None:
        return None
    if any(event.kind in (REJECTED, OFFER) for event in events):
        return None
    if count_upcoming_interviews(events, today) > 0:
        return None  # entretien à venir : on attend de l'avoir passé

    interview_dates = [
        d for d in (_interview_date(e) for e in events if e.kind == INTERVIEW) if d is not None
    ]
    since, delays = SINCE_APPLICATION, schedule.after_application
    last_interview = max(interview_dates, default=None)
    if last_interview is not None and last_interview >= start:
        since, delays, start = SINCE_INTERVIEW, schedule.after_interview, last_interview

    def counts(noted: date) -> bool:
        # Après un entretien, une relance du jour même concernait encore la candidature.
        return noted > start if since == SINCE_INTERVIEW else noted >= start

    reminders = sorted(
        noted
        for noted in (_to_date(e.at) for e in events if e.kind == NO_RESPONSE)
        if noted is not None and counts(noted)
    )
    # La 1re relance notée solde la relance due ce jour-là (la 2e si notée après J+8) ; chacune
    # des suivantes solde la relance d'après.
    done = 0
    if reminders:
        first = reminders[0]
        done = max(1, sum(1 for d in delays if start + timedelta(days=d) <= first))
        done += len(reminders) - 1
    if done >= len(delays):
        return None  # toutes les relances prévues sont soldées (ou aucun délai réglé)
    return _Context(
        since=since,
        start=start,
        delays=delays,
        done=done,
        last_noted=reminders[-1] if reminders else None,
    )


def _due(ctx: _Context, step: int, due_date: date) -> FollowUpDue:
    return FollowUpDue(
        since=ctx.since, start_date=ctx.start, due_date=due_date, step=step, total=len(ctx.delays)
    )


def _current(ctx: _Context, today: date) -> FollowUpDue | None:
    """Relance due aujourd'hui dans ce contexte, ou ``None``."""
    if ctx.last_noted is None:
        # Rien de noté : chaque délai atteint est une relance ; on prend la dernière atteinte.
        reached = [ctx.start + timedelta(days=d) for d in ctx.delays]
        reached = [d for d in reached if d <= today]
        return _due(ctx, len(reached), reached[-1]) if reached else None
    # Relance notée : la suivante tombe le dernier délai réglé après la dernière notée.
    due = ctx.last_noted + timedelta(days=ctx.delays[-1])
    return _due(ctx, ctx.done + 1, due) if due <= today else None


def follow_up_due(
    applied_at: str,
    events: Sequence[TrackingEvent],
    schedule: FollowUpSchedule,
    today: date,
) -> FollowUpDue | None:
    """Relance à faire aujourd'hui pour une candidature, ou ``None`` s'il n'y en a pas."""
    ctx = _context(applied_at, events, schedule, today)
    return _current(ctx, today) if ctx is not None else None


def next_follow_up(
    applied_at: str,
    events: Sequence[TrackingEvent],
    schedule: FollowUpSchedule,
    today: date,
) -> FollowUpDue | None:
    """Prochaine relance **pas encore due** (après aujourd'hui), ou ``None``.

    Rien n'est annoncé tant qu'une relance est due : la date de la suivante dépend du jour où
    celle-ci sera notée.
    """
    ctx = _context(applied_at, events, schedule, today)
    if ctx is None or _current(ctx, today) is not None:
        return None
    if ctx.last_noted is None:
        delay = ctx.delays[0]  # rien d'atteint (sinon une relance serait due)
        return _due(ctx, 1, ctx.start + timedelta(days=delay))
    return _due(ctx, ctx.done + 1, ctx.last_noted + timedelta(days=ctx.delays[-1]))
