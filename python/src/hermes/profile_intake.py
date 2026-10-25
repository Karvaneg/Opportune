"""Runner d'intake de profil — CV PDF → ``CandidateProfile`` persisté (V2, OPP-137).

Rend dogfoodable la chaîne d'OPP-136 : ``python -m hermes.profile_intake ton_cv.pdf`` lit
le PDF, en extrait le texte (OPP-137), l'analyse (``analyze_cv``, OPP-136), fusionne les
**préférences** lues dans l'environnement et **persiste** le profil — en écrasant le seed
d'une recherche (upsert par id) pour que la boucle push tourne enfin sur un profil réel.

``main`` touche le réseau (Ollama), le disque (PDF) et SQLite : non testé (pragma). Le
cœur **pur** — ``resolve_intake_preferences`` — lit et valide l'environnement et se teste
sans IO.
"""

from __future__ import annotations

import os
from typing import Mapping

from app.candidate_profile import CONTRACT_TYPES

# Préférences optionnelles : variable d'env → (clé de profil, convertisseur). Le
# ``contract_type`` est traité à part (obligatoire). Une préférence n'est jamais extraite
# du CV — elle est saisie ici (choix produit acté en OPP-136).
_OPTIONAL_PREFERENCES: dict[str, tuple[str, type]] = {
    "OPPORTUNE_TARGET_SALARY": ("target_salary", float),
    "OPPORTUNE_TARGET_DAILY_RATE": ("target_daily_rate", float),
    "OPPORTUNE_MOBILITY": ("mobility", str),
    "OPPORTUNE_REMOTE": ("remote", str),
    "OPPORTUNE_AVAILABILITY": ("availability", str),
}


def resolve_intake_preferences(
    env: Mapping[str, str],
) -> tuple[str, str | None, dict[str, object]]:
    """Lit ``(contract_type, candidate_id, préférences)`` depuis l'environnement.

    ``OPPORTUNE_CONTRACT_TYPE`` est **obligatoire** et validé au démarrage (fail-fast, avant
    l'extraction PDF et l'appel LLM) : une valeur absente ou hors ``CONTRACT_TYPES`` lève
    ``ValueError``. ``OPPORTUNE_CANDIDATE_ID`` (optionnel) cible le profil à remplacer.
    Les préférences optionnelles absentes/vides sont ignorées ; un nombre mal formé lève
    ``ValueError`` explicite plutôt que d'échouer plus loin.
    """
    contract_type = (env.get("OPPORTUNE_CONTRACT_TYPE") or "").strip()
    if contract_type not in CONTRACT_TYPES:
        raise ValueError(
            f"OPPORTUNE_CONTRACT_TYPE doit être l'un de {CONTRACT_TYPES} "
            f"(reçu {contract_type!r})."
        )

    candidate_id = env.get("OPPORTUNE_CANDIDATE_ID") or None

    preferences: dict[str, object] = {}
    for env_key, (pref_key, converter) in _OPTIONAL_PREFERENCES.items():
        raw = env.get(env_key)
        if raw is None or raw.strip() == "":
            continue
        if converter is float:
            try:
                preferences[pref_key] = float(raw)
            except ValueError:
                raise ValueError(
                    f"{env_key} invalide ({raw!r}) : un nombre est attendu."
                ) from None
        else:
            preferences[pref_key] = raw.strip()
    return contract_type, candidate_id, preferences


def main() -> None:  # pragma: no cover - point d'entrée IO (PDF + Ollama + SQLite)
    """Entrée CLI : ``python -m hermes.profile_intake <cv.pdf>`` (ou ``OPPORTUNE_CV_PATH``).

    Variables : ``OPPORTUNE_CONTRACT_TYPE`` (obligatoire), ``OPPORTUNE_CANDIDATE_ID``
    (profil à écraser, p. ex. ``ma-recherche``), préférences optionnelles (cf.
    ``_OPTIONAL_PREFERENCES``), ``OPPORTUNE_LLM_TIMEOUT`` et ``OLLAMA_*`` (via ``app.llm``).
    """
    import sys

    from app.db import connect
    from app.candidate_profile import ProfileValidationError
    from app.llm_client import OllamaLLMClient
    from app.profile_analysis import ProfileAnalysisError
    from app.profile_intake_service import intake_profile
    from app.profile_store import ProfileStore

    from app.llm import resolve_llm_timeout

    from hermes.pdf_extract import PdfExtractionError, extract_text_from_pdf

    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OPPORTUNE_CV_PATH")
    if not path:
        raise SystemExit(
            "Chemin du CV PDF manquant : `python -m hermes.profile_intake <cv.pdf>` "
            "(ou variable OPPORTUNE_CV_PATH)."
        )

    try:
        contract_type, candidate_id, preferences = resolve_intake_preferences(os.environ)
    except ValueError as err:
        raise SystemExit(str(err)) from err

    try:
        cv_text = extract_text_from_pdf(path)
    except (PdfExtractionError, ValueError, OSError) as err:
        raise SystemExit(f"Extraction PDF échouée : {err}") from err

    client = OllamaLLMClient(timeout=resolve_llm_timeout(os.environ))
    try:
        profile = intake_profile(
            cv_text,
            contract_type=contract_type,
            client=client,
            store=ProfileStore(connect()),
            id=candidate_id,
            **preferences,
        )
    except (ProfileAnalysisError, ProfileValidationError) as err:
        raise SystemExit(f"Profil non construit : {err}") from err

    years = profile.total_experience_years
    print(
        f"✅ Profil {profile.id} : {profile.name} — {len(profile.skills)} compétence(s), "
        f"{years if years is not None else '?'} an(s) d'expérience, contrat {profile.contract_type}."
    )
    print(f"   skills : {', '.join(profile.skills)}")


if __name__ == "__main__":  # pragma: no cover
    main()
