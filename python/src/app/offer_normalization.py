"""Normalisation déterministe des champs d'une offre (V2, OPP-037).

Fonctions **pures** (aucun LLM, aucune I/O) appliquées à la sortie d'analyse avant
de construire une ``Offer`` : canonicalisation du type de contrat, nettoyage de la
localisation et dédoublonnage des compétences. Un type de contrat inconnu est
conservé tel quel (nettoyé) plutôt qu'écrasé, pour ne pas perdre d'information.
"""

from __future__ import annotations

# Synonymes (en minuscules) → forme canonique du type de contrat.
_CONTRACT_SYNONYMS = {
    "cdi": "CDI",
    "contrat à durée indéterminée": "CDI",
    "permanent": "CDI",
    "cdd": "CDD",
    "contrat à durée déterminée": "CDD",
    "freelance": "Freelance",
    "indépendant": "Freelance",
    "independant": "Freelance",
    "mission": "Freelance",
    "consultant": "Freelance",
    "stage": "Stage",
    "internship": "Stage",
    "alternance": "Alternance",
    "apprentissage": "Alternance",
    "intérim": "Intérim",
    "interim": "Intérim",
}


def normalize_contract(value: str) -> str:
    """Canonicalise un type de contrat ; conserve la valeur nettoyée si inconnu."""
    cleaned = " ".join(value.split())
    return _CONTRACT_SYNONYMS.get(cleaned.lower(), cleaned)


def normalize_location(value: str) -> str:
    """Nettoie une localisation (espaces superflus réduits)."""
    return " ".join(value.split())


def normalize_skills(skills: list[str]) -> list[str]:
    """Nettoie et dédoublonne des compétences (insensible à la casse, ordre conservé)."""
    seen: set[str] = set()
    result: list[str] = []
    for skill in skills:
        cleaned = " ".join(skill.split())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result
