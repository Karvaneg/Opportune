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


# --- Filtrage du bruit d'extraction de skills (OPP-142) ----------------------
# Le petit modèle local extrait parfois comme « skills » des éléments qui n'en
# sont pas. La consigne du prompt (cf. ``offer_analysis_service``) réduit ce bruit
# sans le garantir : ce filet déterministe, volontairement CONSERVATEUR, ne vise
# que les catégories non ambiguës listées au ticket, pour ne pas perdre de vraies
# compétences de niche. Symétrique d'OPP-135 (atomisation), mais côté filtrage.

# Normes/labels et organismes/partenaires qui ne sont pas des compétences. Le
# match porte sur la compétence ENTIÈRE (casse-insensible) : « Microsoft » seul
# est écarté, mais « Microsoft Azure » (techno concrète) survit.
_NON_SKILL_TERMS = frozenset(
    {
        # normes / labels
        "iso",
        "pef",
        "wcag",
        "rgaa",
        "affichage environnemental",
        # organismes / partenaires
        "unesco",
        "ademe",
        "greentech",
        "microsoft",
    }
)

# Tâches/formulations métier : une compétence qui COMMENCE par une nominalisation
# d'action suivie d'un connecteur « de/des/du/d' » décrit une mission, pas une
# techno (« Optimisation de calculs », « Gestion des droits utilisateurs »,
# « Parsing de documents », « Traitement de données hétérogènes »). Volontairement
# restreint aux verbes d'action sans ambiguïté : on écarte les nominalisations
# trop génériques (« analyse », « suivi », « pilotage »…) qui attrapent de vraies
# compétences (« Analyse de données », « Analyse de risques »).
_TASK_PREFIXES = (
    "optimisation",
    "gestion",
    "conception",
    "parsing",
    "traitement",
    "développement",
    "création",
    "rédaction",
    "maintenance",
    "déploiement",
    "amélioration",
    "réalisation",
    "élaboration",
    "mise en place",
)
# NB : « de la »/« de l' » sont déjà couverts par « es? » (match « de » + limite de
# mot sur l'espace suivant) — inutile de les lister à part.
_TASK_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in _TASK_PREFIXES) + r")\s+d(?:es?|u|')\b",
    re.IGNORECASE,
)

# Compléments « métier » qui dénotent une compétence reconnue malgré un préfixe
# d'action : « Gestion de projet », « Conception de systèmes », « Développement de
# logiciels » sont des compétences, pas des missions — contrairement à « … de
# calculs / de documents / de données hétérogènes », qui restent du bruit.
_SKILL_COMPLEMENTS = frozenset(
    {
        "projet",
        "projets",
        "produit",
        "produits",
        "système",
        "systèmes",
        "logiciel",
        "logiciels",
    }
)


def _is_non_skill(skill: str) -> bool:
    """Vrai si ``skill`` est du bruit (norme/organisme connu ou tâche formulée)."""
    if skill.lower() in _NON_SKILL_TERMS:
        return True
    match = _TASK_RE.match(skill)
    if match is None:
        return False
    # Un complément métier reconnu (« … de projet/système/logiciel ») désigne une
    # vraie compétence, pas une mission : dans ce cas on ne filtre pas.
    rest = skill[match.end() :].split()
    return not (rest and rest[0].lower() in _SKILL_COMPLEMENTS)


def drop_non_skills(skills: list[str]) -> list[str]:
    """Retire le bruit d'extraction (normes, organismes, tâches) — OPP-142.

    Filet déterministe conservateur : ne supprime que les catégories évidentes,
    pour que le dénominateur de ``compare_skills`` reflète la vraie adéquation
    technique. Ordre et casse des compétences conservées sont préservés.
    """
    return [skill for skill in skills if not _is_non_skill(skill)]
