"""Modèle de profil candidat (V2, OPP-017).

Portage Python du profil candidat (cf. Node ``src/models/userProfile.js``) : structure,
valeurs par défaut neutres et **validation stricte** des champs obligatoires. Le profil
sert de référence au futur matching profil ↔ offre (skills, type de contrat,
expérience, localisation, prétentions).

Ce module ne parle ni au LLM ni à SQLite : il fixe le contrat de données et valide.
La persistance vit dans ``profile_store``.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date

# Types de contrat reconnus (préférence du candidat).
CONTRACT_TYPES = ("CDI", "freelance", "les deux")

# Disponibilités reconnues (échelle fermée) ; sinon une date ISO (YYYY-MM-DD).
AVAILABILITY_OPTIONS = ("immédiate", "sous 1 mois", "sous 3 mois")

# Champs sans lesquels le profil n'est pas exploitable par l'analyse d'offres.
REQUIRED_FIELDS = ("name", "skills", "contract_type")


class ProfileValidationError(Exception):
    """Les données fournies ne forment pas un profil candidat valide."""


@dataclass(frozen=True)
class CandidateProfile:
    """Profil candidat standardisé."""

    id: str
    name: str
    skills: list[str]
    contract_type: str
    structured_skills: list[dict] = field(default_factory=list)
    experiences: list[dict] = field(default_factory=list)
    total_experience_years: float | None = None
    location: str | None = None
    mobility: str | None = None
    remote: str | None = None
    target_salary: float | None = None
    target_daily_rate: float | None = None
    languages: list[str] = field(default_factory=list)
    availability: str | None = None
    constraints: list[str] = field(default_factory=list)


def _clean_str_list(value: object, field_name: str) -> list[str]:
    """Valide une liste de chaînes, nettoyée et sans entrées vides."""
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ProfileValidationError(f"{field_name} doit être une liste de chaînes")
    return [" ".join(x.split()) for x in value if x.strip()]


def _optional_non_negative(value: object, field_name: str) -> float | None:
    """Valide un nombre ≥ 0 optionnel (``None`` accepté)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ProfileValidationError(f"{field_name} doit être un nombre ≥ 0")
    return float(value)


def _validate_availability(value: object) -> str | None:
    """Valide une disponibilité : option fermée, date ISO, ou ``None``."""
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise ProfileValidationError("availability invalide")
    cleaned = value.strip()
    if cleaned in AVAILABILITY_OPTIONS:
        return cleaned
    # Date ISO stricte YYYY-MM-DD : ``date.fromisoformat`` (Python 3.11+) accepte
    # aussi des formes comme "20261001" ou "2026-W40-3" qu'on refuse ici en
    # exigeant que la forme canonique corresponde à l'entrée.
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ProfileValidationError(
            "availability doit être une option connue ou une date ISO (YYYY-MM-DD)"
        ) from exc
    if parsed.isoformat() != cleaned:
        raise ProfileValidationError(
            "availability doit être une date ISO au format YYYY-MM-DD"
        )
    return cleaned


def create_profile(**data: object) -> CandidateProfile:
    """Construit un profil validé à partir de données partielles.

    Applique les valeurs par défaut neutres et valide strictement les champs
    obligatoires (``name``, ``skills``, ``contract_type``). Lève
    ``ProfileValidationError`` si une contrainte n'est pas respectée.
    """
    name = data.get("name")
    if not isinstance(name, str) or name.strip() == "":
        raise ProfileValidationError("name est obligatoire")

    skills = _clean_str_list(data.get("skills", []), "skills")
    if not skills:
        raise ProfileValidationError("skills doit contenir au moins une compétence")

    contract_type = data.get("contract_type")
    if contract_type not in CONTRACT_TYPES:
        raise ProfileValidationError(
            f"contract_type doit être l'un de {CONTRACT_TYPES}"
        )

    structured = data.get("structured_skills", [])
    if not isinstance(structured, list) or not all(
        isinstance(x, dict) for x in structured
    ):
        raise ProfileValidationError("structured_skills doit être une liste d'objets")
    experiences = data.get("experiences", [])
    if not isinstance(experiences, list) or not all(
        isinstance(x, dict) for x in experiences
    ):
        raise ProfileValidationError("experiences doit être une liste d'objets")

    profile_id = data.get("id")
    if profile_id is not None and (
        not isinstance(profile_id, str) or profile_id.strip() == ""
    ):
        raise ProfileValidationError("id, si fourni, doit être une chaîne non vide")

    return CandidateProfile(
        id=profile_id or str(uuid.uuid4()),
        name=name.strip(),
        skills=skills,
        contract_type=contract_type,
        structured_skills=deepcopy(structured),
        experiences=deepcopy(experiences),
        total_experience_years=_optional_non_negative(
            data.get("total_experience_years"), "total_experience_years"
        ),
        location=_optional_str(data.get("location")),
        mobility=_optional_str(data.get("mobility")),
        remote=_optional_str(data.get("remote")),
        target_salary=_optional_non_negative(data.get("target_salary"), "target_salary"),
        target_daily_rate=_optional_non_negative(
            data.get("target_daily_rate"), "target_daily_rate"
        ),
        languages=_clean_str_list(data.get("languages", []), "languages"),
        availability=_validate_availability(data.get("availability")),
        constraints=_clean_str_list(data.get("constraints", []), "constraints"),
    )


def _optional_str(value: object) -> str | None:
    """Nettoie une chaîne optionnelle (``None`` si absente/vide)."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProfileValidationError("champ texte attendu")
    cleaned = " ".join(value.split())
    return cleaned or None


def update_profile(profile: CandidateProfile, **changes: object) -> CandidateProfile:
    """Retourne une copie validée du profil avec les changements appliqués.

    L'``id`` reste stable (un changement d'``id`` est ignoré). Les modifications
    repassent par la **même validation** que ``create_profile`` : impossible de
    corrompre un profil (type de contrat inconnu, ``skills`` vide, nombre négatif…)
    via une mise à jour.
    """
    changes.pop("id", None)
    data = asdict(profile)
    data.update(changes)
    return create_profile(**data)
