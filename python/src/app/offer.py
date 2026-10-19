"""Modèle d'offre standardisée (V2, OPP-037).

``Offer`` est l'offre normalisée et persistable, dérivée d'une ``OfferAnalysis`` : on
normalise contrat/localisation/compétences, on conserve les données d'origine
(``raw_text``) et la provenance (``source``, ``url``), et on lui attribue un **id
stable** dérivé de la provenance (``url`` en priorité, sinon le ``raw_text`` d'origine)
— ce qui permet l'upsert (ré-analyser la même offre met à jour la ligne au lieu de la
dupliquer), y compris quand le LLM reformule le titre entre deux analyses.

**L'identité ne dépend jamais d'une sortie du LLM** (``title``/``company``, non
déterministes) : sans url, ré-ingérer le même texte collé produirait sinon un doublon
dès que le modèle reformule le titre. On s'appuie donc sur le texte brut, invariant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.offer_analysis import OfferAnalysis
from app.offer_kind import DEFAULT_KIND, resolve_kind
from app.offer_normalization import (
    drop_non_skills,
    normalize_contract,
    normalize_location,
    normalize_skills,
)
from app.url_canonical import canonicalize_url


def compute_offer_id(source: str, url: str, raw_text: str) -> str:
    """Identifiant stable d'une offre, indépendant de toute sortie du LLM.

    Quand une ``url`` est fournie, sa forme **canonique** (``canonicalize_url``) sert
    seule de discriminant (avec la ``source``) : l'id reste **stable** même si le LLM
    reformule le titre à la ré-analyse, et deux liens vers la même offre qui ne diffèrent
    que par des paramètres de tracking (``utm_*``…), l'ordre des paramètres ou un slash
    final donnent le **même** id (dédup « même offre, deux liens » — OPP-119). Sans url
    (offre collée), on retombe sur le ``raw_text`` d'origine — invariant déterministe,
    antérieur à l'analyse : ré-ingérer le même texte donne le même id (donc un upsert, pas
    un doublon), quelle que soit la reformulation du LLM.

    Le texte brut est **normalisé** (casse ignorée, suites d'espaces/retours ligne
    réduites à une espace) pour qu'un simple reformatage du collage — repli de lignes,
    espaces en trop — ne fabrique pas une offre distincte.
    """
    identity = canonicalize_url(url) or " ".join(raw_text.split()).lower()
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
    # Type d'offre (OPP-166) : ``emploi`` (défaut) ou ``formation``. Une formation n'est pas
    # scorée sur l'adéquation des compétences (cf. ``offer_score``) — mesurer « compétences
    # requises ↔ détenues » n'a pas de sens pour un cursus dont le but est de les acquérir.
    kind: str = DEFAULT_KIND
    # Date d'ingestion (ISO 8601 UTC), renseignée par la **persistance** au premier
    # enregistrement (OPP-152) — pas une donnée métier dérivée du LLM, donc défaut vide
    # ici et absente de ``from_analysis`` : c'est ``OfferStore`` qui l'attribue et la relit.
    created_at: str = ""

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
            id=compute_offer_id(source, url, raw_text),
            title=analysis.title,
            company=analysis.company,
            location=normalize_location(analysis.location),
            skills=drop_non_skills(normalize_skills(analysis.skills)),
            seniority=analysis.seniority,
            contract_type=normalize_contract(analysis.contract_type),
            summary=analysis.summary,
            attention_points=list(analysis.attention_points),
            source=source.strip(),
            url=url.strip(),
            raw_text=raw_text,
            # Type arbitré à l'intake : proposition du LLM (``analysis.kind``) corrigée par
            # l'heuristique sur le titre/texte (prioritaire sur un signal de formation).
            kind=resolve_kind(analysis.kind, analysis.title, raw_text),
        )
