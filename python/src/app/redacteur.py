"""Port Rédacteur : génération de documents de candidature (V2, OPP-113).

Le port ``Redacteur`` découple le **moteur de rédaction** du reste du back : le métier
dépend de cette interface, jamais d'Ollama en direct. Première capacité livrée : la
**lettre de motivation**, à partir d'une offre et du profil candidat.

Implémentation par défaut ``LLMRedacteur``, adossée au contrat ``LLMClient`` (OPP-079 :
Ollama/Ministral par défaut, transport ``urllib`` injectable, zéro dépendance). Le
prompt est une **fonction pure et déterministe** (offre + profil → texte), donc
directement testable ; en test on injecte un ``MockLLMClient`` — aucun appel réseau,
aucun serveur Ollama requis.

Swapper le moteur se fait à deux niveaux : le transport/modèle LLM via la config de
``LLMClient`` (``OLLAMA_HOST`` / ``OLLAMA_MODEL``), et la stratégie de rédaction
elle-même via une autre implémentation du port ``Redacteur``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.candidate_profile import CandidateProfile
from app.cover_letter import CoverLetter
from app.llm_client import LLMClient
from app.offer import Offer

# Consigne déterministe : une lettre FR prête à relire, sans préambule ni JSON, fondée
# sur les seules données fournies. Séparée des données pour rester testable.
_INSTRUCTIONS = (
    "Tu es candidat(e) et tu rédiges une lettre de motivation en français pour "
    "postuler à l'offre ci-dessous, en t'appuyant sur ton profil.\n"
    "Contraintes :\n"
    "- Réponds UNIQUEMENT par le corps de la lettre, sans préambule, sans commentaire, "
    "sans balise ni JSON.\n"
    "- Vouvoiement, ton professionnel et sincère ; 3 à 4 paragraphes concis.\n"
    "- Mets en avant l'adéquation entre le profil et l'offre (compétences, expériences).\n"
    "- N'invente aucune information absente du profil ; reste sobre si une donnée manque, "
    "et n'insère aucun champ à compléter entre crochets.\n\n"
)


def _format_list(values: list[str]) -> str:
    """Rend une liste de chaînes en énumération lisible (vide → « Non précisé »)."""
    cleaned = [v.strip() for v in values if isinstance(v, str) and v.strip()]
    return ", ".join(cleaned) if cleaned else "Non précisé"


def _format_value(value: object) -> str:
    """Rend une valeur de sous-champ pour le prompt : les listes (p. ex. ``highlights``,
    ``skills`` d'une expérience) sont aplaties en énumération lisible plutôt que laissées
    en ``repr`` Python (``['a', 'b']`` → ``a, b``)."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _format_dicts(items: list[dict]) -> list[str]:
    """Rend une liste d'objets (expériences, compétences structurées) en lignes.

    Chaque objet devient ``- clé: valeur ; clé: valeur`` dans l'ordre de ses clés
    (déterministe). Les valeurs liste sont aplaties (cf. ``_format_value``). Les objets
    vides sont ignorés.
    """
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict) or not item:
            continue
        pairs = "; ".join(
            f"{key}: {_format_value(value)}" for key, value in item.items()
        )
        lines.append(f"- {pairs}")
    return lines


def _format_profile(profile: CandidateProfile) -> str:
    """Bloc profil déterministe : n'inclut que les champs renseignés."""
    lines = [
        f"Nom : {profile.name}",
        f"Type de contrat recherché : {profile.contract_type}",
        f"Compétences : {_format_list(profile.skills)}",
    ]
    if profile.total_experience_years is not None:
        lines.append(f"Années d'expérience : {profile.total_experience_years:g}")
    if profile.location:
        lines.append(f"Localisation : {profile.location}")
    if profile.languages:
        lines.append(f"Langues : {_format_list(profile.languages)}")
    if profile.availability:
        lines.append(f"Disponibilité : {profile.availability}")
    if profile.constraints:
        lines.append(f"Contraintes : {_format_list(profile.constraints)}")
    experiences = _format_dicts(profile.experiences)
    if experiences:
        lines.append("Expériences :")
        lines.extend(experiences)
    return "\n".join(lines)


def _format_offer(offer: Offer) -> str:
    """Bloc offre déterministe, fondé sur les champs normalisés de l'analyse."""
    lines = [
        f"Intitulé : {offer.title}",
        f"Entreprise : {offer.company}",
        f"Localisation : {offer.location}",
        f"Type de contrat : {offer.contract_type}",
        f"Séniorité : {offer.seniority}",
        f"Compétences attendues : {_format_list(offer.skills)}",
        f"Résumé : {offer.summary}",
    ]
    if offer.attention_points:
        lines.append(f"Points d'attention : {_format_list(offer.attention_points)}")
    return "\n".join(lines)


def build_cover_letter_prompt(offer: Offer, profile: CandidateProfile) -> str:
    """Construit le prompt de lettre de motivation (pur et déterministe)."""
    return (
        _INSTRUCTIONS
        + "=== Offre ===\n"
        + _format_offer(offer)
        + "\n\n=== Profil du candidat ===\n"
        + _format_profile(profile)
    )


@runtime_checkable
class Redacteur(Protocol):
    """Contrat de rédaction consommé par le métier.

    Première capacité : produire une ``CoverLetter`` à partir d'une offre et d'un
    profil. Les implémentations lèvent ``CoverLetterError`` si la génération est
    inexploitable, et ``LLMError`` (ou une sous-classe) en cas d'échec du moteur.
    """

    def write_cover_letter(
        self, offer: Offer, profile: CandidateProfile
    ) -> CoverLetter: ...


class LLMRedacteur:
    """Implémentation par défaut du port, adossée au contrat ``LLMClient``.

    Compose le prompt déterministe (offre + profil) puis délègue la génération au
    ``client`` LLM injecté. Aucun couplage à Ollama ni au réseau : en test, un
    ``MockLLMClient`` suffit.

    Note de câblage : une lettre complète est bien plus longue qu'une analyse d'offre
    et peut dépasser le ``DEFAULT_TIMEOUT`` (60 s) du client sur une machine modeste.
    Le wiring réel doit donc fournir un ``OllamaLLMClient(timeout=…)`` généreux.
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    def write_cover_letter(
        self, offer: Offer, profile: CandidateProfile
    ) -> CoverLetter:
        prompt = build_cover_letter_prompt(offer, profile)
        response = self._client.generate(prompt)
        return CoverLetter.from_generation(
            response.text, model=response.model, raw=response.raw
        )
