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

# Schéma d'une expérience professionnelle extraite du CV (OPP-173). ``period`` est une
# chaîne **libre** (« 2021 – 2024 », « depuis 2022 ») : les CV expriment les dates de
# façon trop variée pour imposer des bornes strictes, et l'affichage littéral suffit à un
# CV. ``highlights`` porte les réalisations/missions, une phrase par élément. ``location``
# et ``skills`` sont facultatifs.
_EXPERIENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "company": {"type": "string"},
        "period": {"type": "string"},
        "location": {"type": "string"},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "company", "period", "highlights"],
}

# Schéma JSON dérivé des mêmes champs, pour contraindre le décodage du LLM
# (« structured outputs » d'Ollama, cf. OPP-133). ``total_experience_years`` est un
# nombre **ou null** : un CV ne permet pas toujours d'estimer un total d'années, et 0 an
# (débutant) est une valeur légitime distincte de « inconnu ». ``experiences`` est la liste
# structurée du parcours (OPP-173), éventuellement vide.
PROFILE_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "string"} for name in _TEXT_FIELDS},
        **{name: {"type": "array", "items": {"type": "string"}} for name in _LIST_FIELDS},
        "total_experience_years": {"type": ["number", "null"]},
        "experiences": {"type": "array", "items": _EXPERIENCE_SCHEMA},
    },
    "required": [
        *_TEXT_FIELDS,
        *_LIST_FIELDS,
        "total_experience_years",
        "experiences",
    ],
}


class ProfileAnalysisError(Exception):
    """La réponse fournie n'est pas une analyse de CV exploitable."""


@dataclass(frozen=True)
class ProfileAnalysis:
    """Faits extraits d'un CV (préférences exclues).

    ``skills`` et ``languages`` peuvent être vides ; ``name`` et ``location`` sont
    toujours renseignés (le prompt impose « Non précisé » à défaut) ;
    ``total_experience_years`` vaut ``None`` si le CV ne permet pas de l'estimer.
    ``experiences`` est le parcours structuré (OPP-173), éventuellement vide ; chaque
    entrée est normalisée à ``title``/``company``/``period``/``highlights`` (+ ``location``
    et ``skills`` si présents).
    """

    name: str
    location: str
    skills: list[str]
    languages: list[str]
    total_experience_years: float | None
    experiences: list[dict]

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
        values["experiences"] = _clean_experiences(data.get("experiences"))
        return cls(**values)  # type: ignore[arg-type]


def _clean_text(value: object) -> str:
    """Normalise un champ texte d'expérience : espaces compactés, ``""`` si absent."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def _clean_str_items(value: object) -> list[str]:
    """Nettoie une liste de chaînes (highlights, skills), entrées vides écartées.

    Tolérante : une valeur absente ou mal typée donne une liste vide plutôt qu'une erreur
    — on n'invente rien, on ne casse pas l'analyse sur un sous-champ dégradé.
    """
    if not isinstance(value, list):
        return []
    return [" ".join(x.split()) for x in value if isinstance(x, str) and x.strip()]


def _clean_experiences(value: object) -> list[dict]:
    """Valide et normalise le parcours extrait du CV (OPP-173).

    ``None`` ou champ absent → ``[]`` (un CV peut ne lister aucune expérience). Chaque
    élément doit être un objet ; il est ramené à une forme stable
    (``title``/``company``/``period``/``highlights``, plus ``location``/``skills`` si
    renseignés). Les entrées **entièrement vides** sont écartées comme du bruit : garde-fou
    anti-hallucination — on n'invente jamais de contenu pour combler un trou.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileAnalysisError("experiences doit être une liste d'objets")
    cleaned: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            raise ProfileAnalysisError("experiences : chaque élément doit être un objet")
        title = _clean_text(item.get("title"))
        company = _clean_text(item.get("company"))
        period = _clean_text(item.get("period"))
        location = _clean_text(item.get("location"))
        highlights = _clean_str_items(item.get("highlights"))
        skills = _clean_str_items(item.get("skills"))
        if not (title or company or period or highlights or skills):
            continue
        entry: dict = {
            "title": title,
            "company": company,
            "period": period,
            "highlights": highlights,
        }
        if location:
            entry["location"] = location
        if skills:
            entry["skills"] = skills
        cleaned.append(entry)
    return cleaned


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
