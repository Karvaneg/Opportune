"""Modèle d'analyse d'offre et validation stricte de la réponse LLM (V2, OPP-036).

``OfferAnalysis`` est le résultat métier structuré d'une offre : le texte brut est
transformé (via un LLM, cf. ``offer_analysis_service``) en huit champs normalisés.

Ce module ne parle **pas** au LLM : il fixe le contrat de données et **valide
strictement** un JSON déjà obtenu. Toute réponse malformée, incomplète ou mal typée
est rejetée par ``OfferAnalysisError`` — jamais silencieusement complétée.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.offer_kind import DEFAULT_KIND, OFFER_KINDS

# Champs texte obligatoires (chaîne non vide) et champs liste (liste de chaînes).
_TEXT_FIELDS = ("title", "company", "location", "seniority", "contract_type", "summary")
_LIST_FIELDS = ("skills", "attention_points")

# Schéma JSON dérivé des **mêmes** tuples de champs, pour contraindre le décodage du LLM
# (« structured outputs » d'Ollama : passé en ``format`` de la requête, cf. ``app.llm``).
# Source unique de vérité avec la validation ci-dessous : le schéma qui force le modèle et
# les contrôles qui le vérifient ne peuvent pas diverger. Contraindre les clés et les types
# à la génération épargne au petit modèle local le JSON malformé qui faisait échouer l'intake.
#
# ``kind`` (OPP-166) est une **proposition** de type d'offre (``emploi``/``formation``) : on
# l'offre au modèle via un enum contraint mais on ne la rend **pas** obligatoire — l'intake ne
# doit pas échouer si le petit modèle l'omet, et l'heuristique (``offer_kind.resolve_kind``)
# tranche de toute façon en aval. D'où sa présence en ``properties`` mais pas en ``required``.
OFFER_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "string"} for name in _TEXT_FIELDS},
        **{name: {"type": "array", "items": {"type": "string"}} for name in _LIST_FIELDS},
        "kind": {"type": "string", "enum": list(OFFER_KINDS)},
    },
    "required": [*_TEXT_FIELDS, *_LIST_FIELDS],
}


class OfferAnalysisError(Exception):
    """La réponse fournie n'est pas une analyse d'offre exploitable."""


@dataclass(frozen=True)
class OfferAnalysis:
    """Analyse structurée d'une offre.

    ``skills`` et ``attention_points`` peuvent être vides (une offre sans compétence
    listée ni point d'attention est légitime) ; les six champs texte sont, eux,
    toujours renseignés (le prompt impose « Non précisé » à défaut).
    """

    title: str
    company: str
    location: str
    skills: list[str]
    seniority: str
    contract_type: str
    summary: str
    attention_points: list[str]
    # Type d'offre proposé par le LLM (OPP-166) : ``emploi`` (défaut) ou ``formation``. Champ
    # **optionnel** et lu avec tolérance — une valeur absente ou hors enum retombe sur le défaut
    # sans faire échouer l'analyse. Le type réellement retenu est arbitré à l'intake par
    # ``offer_kind.resolve_kind`` (heuristique sur le titre/texte prioritaire).
    kind: str = DEFAULT_KIND

    @classmethod
    def from_json(cls, text: str) -> "OfferAnalysis":
        """Parse un JSON texte puis valide (``OfferAnalysisError`` si inexploitable)."""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise OfferAnalysisError("Réponse LLM : JSON invalide") from exc
        if not isinstance(data, dict):
            raise OfferAnalysisError("Réponse LLM : un objet JSON est attendu")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "OfferAnalysis":
        """Valide les champs requis d'un dict et construit l'analyse.

        La validation est stricte sur les champs **attendus** (présence + type) mais
        tolérante aux clés **supplémentaires**, simplement ignorées : robustesse en
        lecture face aux variations du LLM (une clé en trop ne fait pas échouer
        l'analyse).
        """
        values: dict[str, object] = {}

        for name in _TEXT_FIELDS:
            value = data.get(name)
            if not isinstance(value, str) or value.strip() == "":
                raise OfferAnalysisError(
                    f"Champ texte requis manquant ou invalide : {name!r}"
                )
            values[name] = value.strip()

        for name in _LIST_FIELDS:
            value = data.get(name)
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise OfferAnalysisError(
                    f"Champ liste requis manquant ou invalide : {name!r}"
                )
            values[name] = [item.strip() for item in value if item.strip()]

        # ``kind`` (OPP-166) : optionnel et tolérant — une valeur hors enum ou absente retombe
        # sur le défaut plutôt que de rejeter l'analyse (le type est de toute façon rejugé à
        # l'intake). On ne le place dans ``values`` que s'il est exploitable, pour laisser jouer
        # le défaut de la dataclass sinon.
        kind = data.get("kind")
        if isinstance(kind, str) and kind.strip() in OFFER_KINDS:
            values["kind"] = kind.strip()

        return cls(**values)  # type: ignore[arg-type]
