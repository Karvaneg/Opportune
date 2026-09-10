"""Matching profil ↔ offre (V2, OPP-038).

Porte en Python la comparaison offre ↔ profil (cf. Node
``src/services/offerProfileComparator.js``) : produit un **constat structuré**,
dimension par dimension, **sans score** (le scoring explicable est un ticket suivant).

Comparaison purement déterministe (aucun LLM, aucune I/O). Le périmètre est borné à
ce que les modèles V2 exposent des deux côtés — ``Offer`` (OPP-037) et
``CandidateProfile`` (OPP-017) : compétences, type de contrat, localisation et
séniorité/expérience. Langues, rémunération et télétravail viendront quand ``Offer``
les portera.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.candidate_profile import CandidateProfile
from app.offer import Offer
from app.skill_matching import canonicalize, expand_skills

# --- Compétences -------------------------------------------------------------


@dataclass(frozen=True)
class SkillMatch:
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def compare_skills(offer: Offer, profile: CandidateProfile) -> SkillMatch:
    """Recouvrement compétences offre vs profil, **moins littéral** (OPP-139).

    Le profil est étendu par ``expand_skills`` (alias + familles : un profil TypeScript/React
    couvre « JavaScript ») ; chaque compétence d'offre est comparée sous forme canonique.
    ``missing`` = exigées par l'offre mais non couvertes. Les libellés d'origine de l'offre
    sont conservés à l'affichage.
    """
    owned = expand_skills(profile.skills)
    matched: list[str] = []
    missing: list[str] = []
    for skill in offer.skills:
        (matched if canonicalize(skill) in owned else missing).append(skill)
    return SkillMatch(matched=matched, missing=missing)


# --- Type de contrat ---------------------------------------------------------

# Types d'offre acceptés selon la préférence du profil (comparaison casse-insensible).
_PROFILE_CONTRACT_TO_OFFER = {
    "cdi": {"cdi"},
    "freelance": {"freelance"},
    "les deux": {"cdi", "freelance"},
}


@dataclass(frozen=True)
class ContractMatch:
    offer: str | None
    profile: str | None
    compatible: bool | None


def compare_contract_type(offer: Offer, profile: CandidateProfile) -> ContractMatch:
    """Compatibilité entre la préférence de contrat du profil et le contrat de l'offre.

    ``compatible`` vaut ``None`` si l'un des deux côtés est absent/inconnu.
    """
    offer_type = offer.contract_type or None
    profile_type = profile.contract_type or None
    if offer_type is None or profile_type is None:
        return ContractMatch(offer=offer_type, profile=profile_type, compatible=None)
    accepted = _PROFILE_CONTRACT_TO_OFFER.get(profile_type.lower(), set())
    return ContractMatch(
        offer=offer_type,
        profile=profile_type,
        compatible=offer_type.lower() in accepted,
    )


# --- Localisation ------------------------------------------------------------

# Marqueurs de forte mobilité géographique dans le champ libre ``profile.mobility``.
_MOBILITY_MARKERS = re.compile(
    r"\bmobile\b|mobilit[ée]|france enti[èe]re|toute la france|partout|national|"
    r"d[ée]placements?",
    re.IGNORECASE,
)

# Marqueurs de négation : « non mobile », « pas de déplacements », « aucune
# mobilité »… Leur présence désamorce les marqueurs de mobilité (heuristique v1
# prudente : en cas de négation, on ne requalifie pas un écart de lieu).
_NEGATION_MARKERS = re.compile(r"\b(non|pas|aucune?|sans|jamais)\b", re.IGNORECASE)

# Marqueurs de télétravail **côté offre** : une offre remote-friendly désamorce un écart
# de lieu, même si le profil n'est pas explicitement mobile. NB : « hybride » impose une
# présence partielle sur site — on le traite comme non bloquant (heuristique permissive
# assumée), à raffiner quand le lieu pèsera davantage dans le scoring (poids actuel 0.1).
_OFFER_REMOTE_MARKERS = re.compile(
    r"t[ée]l[ée]travail|remote|distanciel|hybride|home\s*office|full\s*remote",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LocationMatch:
    offer: str | None
    profile: str | None
    status: str  # match | mismatch | not_blocking | unknown
    reason: str | None = None


def _is_highly_mobile(profile: CandidateProfile) -> bool:
    mobility = profile.mobility
    if not isinstance(mobility, str) or not _MOBILITY_MARKERS.search(mobility):
        return False
    # Une négation (« non mobile », « pas de déplacements ») annule le marqueur.
    return not _NEGATION_MARKERS.search(mobility)


def _offer_allows_remote(offer: Offer) -> bool:
    """L'offre propose-t-elle du télétravail ?

    Le télétravail est rarement dans le champ ``location`` (souvent une ville) : on cherche
    les marqueurs aussi dans ``title``, ``summary`` et ``attention_points``, là où il est
    réellement mentionné.
    """
    parts: list[str] = [offer.location, offer.title, offer.summary, *offer.attention_points]
    haystack = " ".join(part for part in parts if isinstance(part, str))
    return bool(_OFFER_REMOTE_MARKERS.search(haystack))


def compare_location(offer: Offer, profile: CandidateProfile) -> LocationMatch:
    """Compare les lieux ; un profil mobile **ou une offre en télétravail** rend l'écart non bloquant."""
    base_offer = offer.location or None
    base_profile = profile.location or None

    offer_loc = base_offer.lower() if base_offer else None
    prof_loc = base_profile.lower() if base_profile else None

    # NOTE (v1) : match par sous-chaîne — robuste pour « Paris » ⊂ « Paris 15e »,
    # mais fragile (« Nice » ⊂ « Venice »). À affiner quand le lieu servira au scoring.
    if offer_loc and prof_loc and (
        offer_loc == prof_loc or offer_loc in prof_loc or prof_loc in offer_loc
    ):
        return LocationMatch(base_offer, base_profile, "match")

    if _is_highly_mobile(profile):
        return LocationMatch(base_offer, base_profile, "not_blocking", "profile-mobility")

    # Télétravail proposé par l'offre → l'écart géographique ne bloque pas.
    if _offer_allows_remote(offer):
        return LocationMatch(base_offer, base_profile, "not_blocking", "offer-remote")

    if offer_loc and prof_loc:
        return LocationMatch(base_offer, base_profile, "mismatch")

    return LocationMatch(base_offer, base_profile, "unknown")


# --- Séniorité / expérience --------------------------------------------------

# Labels de séniorité (offre, texte libre) → seuil indicatif d'années d'expérience.
_SENIORITY_YEARS = {
    "junior": 0,
    "débutant": 0,
    "graduate": 0,
    "entry": 0,
    "confirmé": 3,
    "intermédiaire": 3,
    "mid": 3,
    "mid-level": 3,
    "senior": 5,
    "sénior": 5,
    "lead": 8,
    "principal": 8,
    "staff": 8,
    "expert": 8,
}

# Valeurs de séniorité équivalant à « aucune exigence ».
_SENIORITY_NONE = {"", "non précisé", "non precise", "n/a", "aucune"}

# Marqueurs d'**exclusion** de niveau (« pas de junior », « débutants s'abstenir/exclus ») :
# leur présence rend la plage ambiguë (quel niveau est exclu ?) → non évaluable plutôt que
# trop permissif. Cohérent avec ``_is_highly_mobile`` qui désamorce déjà sur négation.
_SENIORITY_EXCLUSION = re.compile(
    r"\b(?:non|pas|sans|aucune?|jamais)\b|abstenir|exclus?", re.IGNORECASE
)


def _min_required_years(normalized: str) -> int | None:
    """Seuil d'années le plus BAS des niveaux connus cités dans un label de séniorité.

    Gère les **plages** (« Junior à Confirmé », « Confirmé/Senior », « mid-level ») : on
    isole les mots, on retient ceux reconnus dans ``_SENIORITY_YEARS`` et on prend leur
    minimum — interprétation permissive (l'offre accepte dès le niveau le plus bas cité).

    ``None`` si aucun niveau connu n'apparaît, **ou** si le label porte une exclusion
    (« pas de junior », « débutants s'abstenir ») : on refuse d'inférer un seuil bas qui
    contredirait l'exigence, quitte à retomber sur « non évaluable ».
    """
    if _SENIORITY_EXCLUSION.search(normalized):
        return None
    tokens = re.split(r"[^0-9a-zàâäéèêëîïôöûùüç]+", normalized)
    years = [_SENIORITY_YEARS[token] for token in tokens if token in _SENIORITY_YEARS]
    return min(years) if years else None


@dataclass(frozen=True)
class SeniorityMatch:
    offer_label: str | None
    required_years: int | None
    profile_years: float | None
    status: str  # ok | insufficient | unknown | not_required


def compare_seniority(offer: Offer, profile: CandidateProfile) -> SeniorityMatch:
    """Confronte le label de séniorité de l'offre au total d'années du profil."""
    label = offer.seniority
    owned = profile.total_experience_years
    normalized = label.strip().lower() if isinstance(label, str) else ""

    if normalized in _SENIORITY_NONE:
        return SeniorityMatch(label or None, None, owned, "not_required")

    # Label simple (lookup direct) puis, à défaut, plage multi-niveaux (« Junior à
    # Confirmé ») → seuil le plus bas des niveaux cités.
    required = _SENIORITY_YEARS.get(normalized)
    if required is None:
        required = _min_required_years(normalized)
    if required is None:  # aucun niveau connu → non évaluable
        return SeniorityMatch(label or None, None, owned, "unknown")
    if owned is None:  # profil ne déclare pas son total
        return SeniorityMatch(label, required, None, "unknown")
    return SeniorityMatch(
        label, required, owned, "ok" if owned >= required else "insufficient"
    )


# --- Point d'entrée ----------------------------------------------------------


@dataclass(frozen=True)
class OfferProfileMatch:
    """Constat structuré de la comparaison offre ↔ profil (sans score)."""

    skills: SkillMatch
    contract_type: ContractMatch
    location: LocationMatch
    seniority: SeniorityMatch


def match_offer_to_profile(offer: Offer, profile: CandidateProfile) -> OfferProfileMatch:
    """Compare une offre à un profil, dimension par dimension."""
    return OfferProfileMatch(
        skills=compare_skills(offer, profile),
        contract_type=compare_contract_type(offer, profile),
        location=compare_location(offer, profile),
        seniority=compare_seniority(offer, profile),
    )
