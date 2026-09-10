"""Normalisation déterministe des champs d'une offre (V2, OPP-037).

Fonctions **pures** (aucun LLM, aucune I/O) appliquées à la sortie d'analyse avant
de construire une ``Offer`` : canonicalisation du type de contrat, nettoyage de la
localisation et dédoublonnage des compétences. Un type de contrat inconnu est
conservé tel quel (nettoyé) plutôt qu'écrasé, pour ne pas perdre d'information.
"""

from __future__ import annotations

import re

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


# Séparateurs d'énumération « forts » à l'intérieur d'une compétence composée :
# virgule, point-virgule, puce, barre verticale, parenthèses, retour ligne. On
# éclate toujours dessus (« Back-end (PostgreSQL, Express) » → 3 compétences).
_STRONG_SEPARATORS = re.compile(r"[,;·|()\n]+")

# Termes atomiques courants contenant « / » : ne PAS les éclater (faux positifs).
_SLASH_ATOMIC = {"ci/cd", "tcp/ip", "i/o", "a/b", "and/or"}


def _atomize(skill: str) -> list[str]:
    """Éclate une compétence composée en compétences atomiques.

    Filet déterministe derrière la consigne du prompt (cf. ``offer_analysis_service``) :
    même si le LLM émet un bloc composé, on le sépare pour préserver le match exact de
    ``compare_skills``. Le « / » n'est éclaté (« HTML/CSS/JS ») que hors des acronymes
    atomiques connus (« CI/CD », « TCP/IP »).
    """
    parts: list[str] = []
    for chunk in _STRONG_SEPARATORS.split(skill):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.lower() in _SLASH_ATOMIC or "/" not in chunk:
            parts.append(chunk)
        else:
            parts.extend(piece for piece in chunk.split("/") if piece.strip())
    return parts


def normalize_skills(skills: list[str]) -> list[str]:
    """Éclate, nettoie et dédoublonne des compétences (casse-insensible, ordre conservé)."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in skills:
        for skill in _atomize(raw):
            cleaned = " ".join(skill.split())
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
    return result
