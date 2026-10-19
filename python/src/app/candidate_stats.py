"""Agrégats d'avancement par candidat, pour le cockpit (V2, OPP-163 / révisé OPP-164).

Le cockpit affiche un **entonnoir de candidature piloté par les décisions de l'utilisateur**
— et non par la recommandation de l'algo (qui n'est qu'un indice de score par offre). Trois
étapes exclusives, dérivées de la décision humaine et de l'état de candidature :

- **à étudier** : offre en attente de décision (décision ``pending`` ou pas encore prise) ;
- **à postuler** : offre **approuvée** mais pas encore candidatée (ce que j'ai décidé de viser) ;
- **postulé** : candidature **déclarée** (``applied``).

Une offre **rejetée** ou **reportée** sort de l'entonnoir (comptée dans ``offres_total`` mais
dans aucune étape). ``offres_total`` est la taille du pool. Déterministe et pur : ``funnel_stage``
classe une offre, ``build_candidate_stats`` agrège le pool déjà résolu par l'appelant.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.decision import PENDING

APPROVED = "approved"

# Étapes de l'entonnoir (clés stables, partagées avec le front).
A_ETUDIER = "a_etudier"
A_POSTULER = "a_postuler"
POSTULE = "postule"


def funnel_stage(decision_status: str | None, applied: bool) -> str | None:
    """Classe une offre dans l'entonnoir d'après la décision humaine et l'état de candidature.

    Priorité à la candidature : une offre candidatée est ``postulé`` même si sa décision a
    évolué. Une offre sans décision (``None``) est « à étudier » (elle attend ma décision).
    ``rejected`` / ``deferred`` → ``None`` (hors entonnoir).
    """
    if applied:
        return POSTULE
    if decision_status == APPROVED:
        return A_POSTULER
    if decision_status is None or decision_status == PENDING:
        return A_ETUDIER
    return None  # rejected / deferred : écartée de l'entonnoir


@dataclass(frozen=True)
class CandidateStats:
    """Compteurs d'avancement d'un candidat, prêts pour les cartes du cockpit."""

    a_etudier: int
    a_postuler: int
    postule: int
    offres_total: int


def build_candidate_stats(stages: Iterable[str | None]) -> CandidateStats:
    """Agrège les étapes d'entonnoir de **toutes** les offres du pool (une entrée par offre).

    ``stages`` est le résultat de ``funnel_stage`` pour chaque offre du pool (``None`` pour
    les offres hors entonnoir — rejetées/reportées). ``offres_total`` est le cardinal du pool.
    """
    a_etudier = a_postuler = postule = total = 0
    for stage in stages:
        total += 1
        if stage == A_ETUDIER:
            a_etudier += 1
        elif stage == A_POSTULER:
            a_postuler += 1
        elif stage == POSTULE:
            postule += 1
    return CandidateStats(
        a_etudier=a_etudier,
        a_postuler=a_postuler,
        postule=postule,
        offres_total=total,
    )
