"""Pipeline d'analyse de bout en bout (V2, OPP-0392).

Point de convergence des briques d'analyse V2 : d'un **texte d'offre brut** et d'un
**profil candidat**, produit un **dossier de décision** en enchaînant

    intake_offer (analyse LLM → Offer normalisée → SQLite)   [OPP-037]
        → match_offer_to_profile                             [OPP-038]
        → explain_score (score + raisons)                    [OPP-039]
        → recommend_action                                   [OPP-0391]

Ne dépend que de contrats injectables (``LLMClient``, ``OfferRepository``) : testable
de bout en bout avec un faux LLM et une fausse persistance. Une analyse invalide
n'entraîne aucune persistance (l'échec se propage avant l'enregistrement, cf.
``intake_offer``).

Périmètre borné au **dossier de décision** : ni génération de documents, ni
candidature, ni suivi (leurs modèles ne sont pas encore portés en V2).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.candidate_profile import CandidateProfile
from app.llm_client import LLMClient
from app.offer import Offer
from app.offer_intake_service import intake_offer
from app.offer_profile_match import OfferProfileMatch, match_offer_to_profile
from app.offer_recommendation import (
    DEFAULT_HIGH,
    DEFAULT_MEDIUM,
    Recommendation,
    recommend_action,
    validate_thresholds,
)
from app.offer_score import ScoreExplanation, explain_score
from app.offer_store import OfferRepository


@dataclass(frozen=True)
class DecisionDossier:
    """Résultat complet du pipeline pour une offre confrontée à un profil."""

    offer: Offer
    match: OfferProfileMatch
    explanation: ScoreExplanation
    recommendation: Recommendation


def run_pipeline(
    raw_text: str,
    *,
    source: str,
    profile: CandidateProfile,
    client: LLMClient,
    store: OfferRepository,
    url: str = "",
    high: int = DEFAULT_HIGH,
    medium: int = DEFAULT_MEDIUM,
) -> DecisionDossier:
    """Déroule le pipeline complet pour une offre brute confrontée à ``profile``.

    Persiste l'offre analysée (via ``store``) puis produit le dossier de décision.
    Propage ``ValueError`` (entrée vide, seuils incohérents), ``OfferAnalysisError``
    (analyse non conforme) et les erreurs du client LLM ; en cas d'échec, rien n'est
    persisté (les seuils sont validés *avant* toute persistance).
    """
    # Valider les seuils en amont : un échec ne doit laisser aucune offre persistée.
    validate_thresholds(high, medium)
    offer = intake_offer(raw_text, source=source, url=url, client=client, store=store)
    match = match_offer_to_profile(offer, profile)
    explanation = explain_score(match)
    recommendation = recommend_action(explanation.score, high=high, medium=medium)
    return DecisionDossier(
        offer=offer, match=match, explanation=explanation, recommendation=recommendation
    )


@dataclass(frozen=True)
class OfferInput:
    """Une offre brute à traiter (texte + provenance)."""

    raw_text: str
    source: str
    url: str = ""


def run_pipeline_batch(
    offers: list[OfferInput],
    *,
    profile: CandidateProfile,
    client: LLMClient,
    store: OfferRepository,
    high: int = DEFAULT_HIGH,
    medium: int = DEFAULT_MEDIUM,
) -> list[DecisionDossier]:
    """Déroule le pipeline pour un lot d'offres (ordre d'entrée préservé).

    Traitement **séquentiel** : un item en échec (analyse non conforme, erreur LLM)
    interrompt le lot en laissant persistées les offres des items déjà traités. Les
    seuils, eux, sont validés avant toute persistance (aucun effet de bord partiel).
    """
    return [
        run_pipeline(
            item.raw_text,
            source=item.source,
            profile=profile,
            client=client,
            store=store,
            url=item.url,
            high=high,
            medium=medium,
        )
        for item in offers
    ]
