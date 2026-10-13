"""Port d'entrée de la collecte d'offres (V2, OPP-119).

``SourceOffres`` est l'**interface** (port, au sens hexagonal) qui découple les
connecteurs du pipeline de collecte : n'importe quelle source — site d'emploi, plateforme
freelance, flux RSS (OPP-120/121/122), ou une simple source mockée en test — se contente
d'émettre des ``RawOffer``. Le pipeline (``app.offer_collection``) ne connaît que ce
contrat, jamais une source concrète.

Une ``RawOffer`` est l'offre **brute, pré-analyse** : le texte tel que collecté, sa
provenance et, si disponible, son URL. L'analyse LLM, la normalisation et la persistance
sont l'affaire du pipeline, pas de la source — ce qui permet de dédoublonner *avant* tout
appel au LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol, runtime_checkable


@dataclass(frozen=True)
class RawOffer:
    """Offre brute émise par une source, avant analyse.

    ``source`` (provenance, obligatoire) et ``raw_text`` (texte collecté) alimentent
    l'intake existant. ``url`` est facultative : si présente, sa forme canonique sert de
    clé de dédoublonnage (cf. ``compute_offer_id``) ; sinon c'est le texte brut.
    """

    source: str
    raw_text: str
    url: str = ""


@runtime_checkable
class SourceOffres(Protocol):
    """Contrat d'une source d'offres consommée par le pipeline de collecte."""

    def fetch(self) -> Iterable[RawOffer]: ...
