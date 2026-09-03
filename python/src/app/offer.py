"""Modèle d'offre standardisée (V2, OPP-037).

``Offer`` est l'offre normalisée et persistable, dérivée d'une ``OfferAnalysis`` : on
normalise contrat/localisation/compétences, on conserve les données d'origine
(``raw_text``) et la provenance (``source``, ``url``), et on lui attribue un **id
stable** dérivé de la provenance (``url`` en priorité, sinon ``company + title``) — ce
qui permet l'upsert (ré-analyser la même offre met à jour la ligne au lieu de la
dupliquer), y compris quand le LLM reformule le titre entre deux analyses.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.offer_analysis import OfferAnalysis
from app.offer_normalization import (
    normalize_contract,
    normalize_location,
    normalize_skills,
)


def compute_offer_id(source: str, url: str, company: str, title: str) -> str:
    """Identifiant stable d'une offre.

    Quand une ``url`` est fournie, elle sert seule de discriminant (avec la
    ``source``) : l'id reste **stable** même si le LLM reformule le titre à la
    ré-analyse. Sans url, on retombe sur ``company + title`` — le meilleur
    discriminant disponible pour distinguer deux offres et limiter les collisions.
    """
    identity = url.strip().lower() or "\n".join(
        part.strip().lower() for part in (company, title)
    )
    key = source.strip().lower() + "\n" + identity
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Offer:
    """Offre standardisée, prête à être persistée."""

    id: str
    title: str
    company: str
    location: str
    skills: list[str]
    seniority: str
    contract_type: str
    summary: str
    attention_points: list[str]
    source: str
    url: str
    raw_text: str

    @classmethod
    def from_analysis(
        cls,
        analysis: OfferAnalysis,
        *,
        source: str,
        raw_text: str,
        url: str = "",
    ) -> "Offer":
        """Construit une offre normalisée à partir d'une analyse et de sa provenance.

        Lève ``ValueError`` si ``source`` ou ``raw_text`` est vide (champs obligatoires
        pour tracer et rejouer l'offre).
        """
        if not isinstance(source, str) or source.strip() == "":
            raise ValueError("La source de l'offre est requise")
        if not isinstance(raw_text, str) or raw_text.strip() == "":
            raise ValueError("Le texte d'origine de l'offre est requis")

        return cls(
            id=compute_offer_id(source, url, analysis.company, analysis.title),
            title=analysis.title,
            company=analysis.company,
            location=normalize_location(analysis.location),
            skills=normalize_skills(analysis.skills),
            seniority=analysis.seniority,
            contract_type=normalize_contract(analysis.contract_type),
            summary=analysis.summary,
            attention_points=list(analysis.attention_points),
            source=source.strip(),
            url=url.strip(),
            raw_text=raw_text,
        )
