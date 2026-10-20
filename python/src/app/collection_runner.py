"""Briques communes aux runners de collecte (V1, OPP-120).

Le lancement d'une passe et le rendu de son bilan sont **indépendants de la source** : qu'il
s'agisse de France Travail, d'Adzuna ou d'une source future, on lance ``collect_offers`` et on
affiche les mêmes compteurs. Ces deux fonctions sont donc factorisées ici, pour que chaque
runner concret (``france_travail_runner``, ``adzuna_runner``) ne garde que ce qui lui est
propre : lire sa configuration et assembler sa source.
"""

from __future__ import annotations

from typing import Callable

from app.llm_client import LLMClient
from app.offer_collection import (
    CollectionProgress,
    CollectionReport,
    collect_offers,
)
from app.offer_source import SourceOffres
from app.offer_store import OfferRepository


def run_collection(
    source: SourceOffres,
    *,
    llm_client: LLMClient,
    store: OfferRepository,
    on_progress: Callable[[CollectionProgress], None] | None = None,
) -> CollectionReport:
    """Lance une passe de collecte sur une source assemblée ; retourne le bilan.

    Fine enveloppe autour de ``collect_offers`` : présente pour offrir un point d'injection
    testable (source/LLM/dépôt factices) partagé par tous les runners concrets. ``on_progress``
    (OPP-170) est transmis tel quel pour la publication d'avancement d'un job de fond.
    """
    return collect_offers(
        source, client=llm_client, store=store, on_progress=on_progress
    )


def format_report(report: CollectionReport) -> str:
    """Rend le bilan de collecte en une synthèse lisible pour la sortie console."""
    lines = [
        f"Collectées : {report.collected}",
        f"Persistées : {report.stored}",
        f"Doublons   : {report.duplicates}",
        f"Échecs     : {len(report.failures)}",
    ]
    if report.enriched:
        lines.append(
            f"Enrichies  : {report.enriched} "
            f"(dont {report.enriched_recovered} avec compétences récupérées)"
        )
    if report.source_error:
        lines.append(f"Erreur source : {report.source_error}")
    for failure in report.failures:
        lines.append(f"  - échec {failure.raw.url or '(sans url)'} : {failure.error}")
    return "\n".join(lines)
