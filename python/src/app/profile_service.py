"""Service de consultation et d'édition du profil candidat (V2, OPP-158).

Le profil sert au scoring (``RecommendationService``) mais n'était ni lisible ni éditable
depuis l'UI : une compétence réellement maîtrisée mais absente des ``skills`` (ex. HTML/CSS,
Agile, Scrum) faisait sous-scorer les offres. Ce service expose le minimum pour combler ce
trou de données depuis le front :

- ``get`` : lecture du profil d'un candidat (``None`` si aucun profil) ;
- ``update_skills`` : remplacement de la liste de compétences, **normalisée** comme à l'intake
  (``normalize_skills`` : atomisation OPP-135) puis éditée via ``correct_profile`` (OPP-138),
  qui revalide (liste vide → ``ProfileValidationError``) **et verrouille** ``skills``. Le
  verrou est essentiel : sans lui, un ré-intake du CV (``intake_profile``) ré-extrairait les
  compétences et écraserait la curation manuelle — annulant le but de ce service. ``None``
  si le candidat n'a pas de profil.

Le service ne connaît ni HTTP ni SQLite directement : il dépend du port ``ProfileRepository``
(faux en test) et du domaine ``candidate_profile``. Les implications de familles (React ⇒
HTML/CSS) restent gérées par ``skill_matching`` au moment du scoring — ici on ne touche qu'aux
compétences **déclarées**.
"""

from __future__ import annotations

from app.candidate_profile import CandidateProfile
from app.offer_normalization import normalize_skills
from app.profile_correction_service import UnknownProfileError, correct_profile
from app.profile_store import ProfileRepository


class ProfileService:
    """Lecture / édition des compétences d'un profil candidat (OPP-158)."""

    def __init__(self, store: ProfileRepository) -> None:
        self._store = store

    def get(self, candidate_id: str) -> CandidateProfile | None:
        """Profil du candidat, ou ``None`` s'il n'en a pas (le profil est clé par candidat)."""
        return self._store.get(candidate_id)

    def update_skills(self, candidate_id: str, skills: list[str]) -> CandidateProfile | None:
        """Remplace les compétences du profil, les **verrouille**, persiste ; rend le profil.

        ``None`` si le candidat n'a pas de profil (l'appelant répond alors 404). Les compétences
        passent par ``normalize_skills`` (même format qu'à l'intake) puis par ``correct_profile``
        (OPP-138) : celui-ci revalide l'ensemble (``ProfileValidationError`` si la liste est vide,
        remontée en 400) **et** ajoute ``skills`` aux ``locked_fields``, pour qu'un ré-intake du CV
        ne réécrase pas la curation manuelle.
        """
        normalized = normalize_skills(skills)
        try:
            return correct_profile(candidate_id, store=self._store, skills=normalized)
        except UnknownProfileError:
            return None
