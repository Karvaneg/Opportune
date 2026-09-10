"""Modèle d'analyse de CV et validation stricte de la réponse LLM (V2, OPP-136).

``ProfileAnalysis`` est le résultat structuré de l'analyse d'un **CV** : le texte brut
est transformé (via un LLM, cf. ``profile_analysis_service``) en un jeu de **faits**
normalisés — ce que le candidat *a fait*, pas ce qu'il *veut* (les préférences, absentes
d'un CV, sont saisies par l'utilisateur au moment de construire le ``CandidateProfile``).

Symétrique de ``offer_analysis`` (OPP-036) : ce module ne parle **pas** au LLM, il
fixe le contrat de données et **valide strictement** un JSON déjà obtenu. Toute réponse
malformée, incomplète ou mal typée est rejetée par ``ProfileAnalysisError``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# Champs texte obligatoires (chaîne non vide) et champs liste (liste de chaînes).
_TEXT_FIELDS = ("name", "location")
_LIST_FIELDS = ("skills", "languages")

# Schéma JSON dérivé des mêmes champs, pour contraindre le décodage du LLM
# (« structured outputs » d'Ollama, cf. OPP-133). ``total_experience_years`` est un
# nombre **ou null** : un CV ne permet pas toujours d'estimer un total d'années, et 0 an
# (débutant) est une valeur légitime distincte de « inconnu ».
PROFILE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "string"} for name in _TEXT_FIELDS},
        **{name: {"type": "array", "items": {"type": "string"}} for name in _LIST_FIELDS},
        "total_experience_years": {"type": ["number", "null"]},
    },
    "required": [*_TEXT_FIELDS, *_LIST_FIELDS, "total_experience_years"],
}


class ProfileAnalysisError(Exception):
    """La réponse fournie n'est pas une analyse de CV exploitable."""


@dataclass(frozen=True)
class ProfileAnalysis:
    """Faits extraits d'un CV (préférences exclues).

    ``skills`` et ``languages`` peuvent être vides ; ``name`` et ``location`` sont
    toujours renseignés (le prompt impose « Non précisé » à défaut) ;
    ``total_experience_years`` vaut ``None`` si le CV ne permet pas de l'estimer.
    """

    name: str
    location: str
    skills: list[str]
    languages: list[str]
    total_experience_years: float | None

    @classmethod
    def from_json(cls, text: str) -> "ProfileAnalysis":
        """Parse un JSON texte puis valide (``ProfileAnalysisError`` si inexploitable)."""
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ProfileAnalysisError("Réponse LLM : JSON invalide") from exc
        if not isinstance(data, dict):
            raise ProfileAnalysisError("Réponse LLM : un objet JSON est attendu")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileAnalysis":
        """Valide les champs requis d'un dict et construit l'analyse.

        Stricte sur les champs **attendus** (présence + type), tolérante aux clés
        **supplémentaires** (ignorées) : robustesse en lecture face aux variations du LLM.
        """
        values: dict[str, object] = {}

        for name in _TEXT_FIELDS:
            value = data.get(name)
            if not isinstance(value, str) or value.strip() == "":
                raise ProfileAnalysisError(
                    f"Champ texte requis manquant ou invalide : {name!r}"
                )
            values[name] = value.strip()

        for name in _LIST_FIELDS:
            value = data.get(name)
            if not isinstance(value, list) or not all(
                isinstance(item, str) for item in value
            ):
                raise ProfileAnalysisError(
                    f"Champ liste requis manquant ou invalide : {name!r}"
                )
            values[name] = [item.strip() for item in value if item.strip()]

        values["total_experience_years"] = _validate_years(
            data.get("total_experience_years")
        )
        return cls(**values)  # type: ignore[arg-type]


def _validate_years(value: object) -> float | None:
    """Valide un total d'années d'expérience : nombre ≥ 0, ou ``None``.

    ``None`` (CV non concluant) est accepté ; un booléen ou un nombre négatif est rejeté
    plutôt que silencieusement corrigé.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ProfileAnalysisError(
            "total_experience_years doit être un nombre ≥ 0 ou null"
        )
    return float(value)
