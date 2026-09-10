"""Intégration de l'analyse LLM dans la création d'un profil (V2, OPP-136).

Orchestration de bout en bout, côté candidat ::

    texte du CV → analyse LLM → faits + préférences → CandidateProfile → persistance

Symétrique de ``offer_intake_service`` (OPP-037). Ne dépend que de contrats injectables :
``LLMClient`` (OPP-079) pour l'analyse et ``ProfileRepository`` (OPP-017) pour le stockage
— d'où une testabilité complète avec un faux LLM et une fausse persistance, sans réseau ni
SQLite réel. L'extraction du texte depuis un PDF est **en amont** (runner OPP-137).
"""

from __future__ import annotations

from app.candidate_profile import CandidateProfile
from app.llm_client import LLMClient
from app.profile_analysis_service import analyze_cv
from app.profile_store import ProfileRepository


def intake_profile(
    cv_text: str,
    *,
    contract_type: str,
    client: LLMClient,
    store: ProfileRepository,
    id: str | None = None,
    **preferences: object,
) -> CandidateProfile:
    """Analyse un CV, fusionne préférences et faits, persiste le profil ; le retourne.

    ``contract_type`` (obligatoire) et ``preferences`` (target_salary, mobility, remote,
    availability, constraints…) sont fournis par l'appelant — un CV ne les porte pas. Un
    ``id`` explicite permet de **remplacer** un profil existant (upsert : p. ex. écraser le
    seed ``cand-marie`` par le vrai profil). Propage ``ValueError`` (CV vide),
    ``ProfileAnalysisError`` (analyse non conforme), ``ProfileValidationError`` (préférence
    invalide, collision fait/préférence, CV sans compétence) et les erreurs du client LLM.
    En cas d'échec avant ``save``, rien n'est persisté.
    """
    analysis = analyze_cv(cv_text, client)
    profile = CandidateProfile.from_analysis(
        analysis, contract_type=contract_type, id=id, **preferences
    )
    store.save(profile)
    return profile
