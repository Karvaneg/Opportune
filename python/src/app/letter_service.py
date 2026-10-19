"""Service de lettre de motivation : génération, édition, suppression (V2, OPP-147).

Orchestre les briques existantes sans réimplémenter de logique : le ``Redacteur``
(OPP-113) produit la lettre à partir de l'offre et du profil, le ``LetterStore`` la
persiste (clé = ``recommendation_id``). La reco est résolue depuis le ``DecisionStore``
(elle porte ``candidate_id`` et ``offer_id``), d'où l'on charge profil et offre.

Règle produit d'OPP-147 — **l'humain tranche la régénération** : ``generate`` refuse
d'écraser une lettre déjà présente (``LetterExistsError``) tant que l'appelant ne
confirme pas (``overwrite=True``). Le back ne décide donc jamais seul de jeter une lettre
(générée *ou* éditée) ; le front présente le choix. C'est le pendant, côté lettre, de la
validation humaine préservée sur les décisions (OPP-131) et des faits verrouillés d'un
profil corrigé (OPP-138).

Collaborateurs **injectés** (profils, offres, décisions, rédacteur, dépôt, horloge) :
le service se teste intégralement sans réseau ni Ollama (``MockLLMClient`` / faux dépôts).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.decision_store import DecisionRepository
from app.letter import SOURCE_AI, SOURCE_HUMAN, Letter, LetterError
from app.letter_store import LetterRepository
from app.recommendation_service import OfferSource, ProfileSource
from app.redacteur import Redacteur


class UnknownRecommendationError(Exception):
    """Aucune recommandation (décision), ou offre/profil sous-jacent, pour cet id."""


class UnknownLetterError(Exception):
    """Aucune lettre n'est encore attachée à cette recommandation."""


class LetterExistsError(Exception):
    """Une lettre existe déjà : la régénération doit être confirmée par l'humain."""


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LetterService:
    """Génère / édite / supprime la lettre d'une recommandation (adaptateur mince)."""

    def __init__(
        self,
        *,
        letters: LetterRepository,
        decisions: DecisionRepository,
        profiles: ProfileSource,
        offers: OfferSource,
        redacteur: Redacteur,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.letters = letters
        self.decisions = decisions
        self.profiles = profiles
        self.offers = offers
        self.redacteur = redacteur
        self._now = now or _utcnow_iso

    def get(self, recommendation_id: str) -> Letter | None:
        """Retourne la lettre de la reco, ou ``None`` si aucune n'est encore générée."""
        return self.letters.get(recommendation_id)

    def updated_at_for(self, recommendation_ids: list[str]) -> dict[str, str]:
        """``{recommendation_id: updated_at}`` des lettres existantes (lecture en lot, cockpit)."""
        return self.letters.updated_at_by_recommendation(recommendation_ids)

    def generate(
        self, recommendation_id: str, *, overwrite: bool = False
    ) -> tuple[Letter, bool]:
        """Génère (LLM) et persiste la lettre d'une reco ; ``source=ai``.

        Retourne ``(letter, created)`` où ``created`` vaut ``True`` à la première création
        et ``False`` sur régénération — l'appelant HTTP en tire le statut 201/200 sans
        relire le dépôt (il connaît déjà l'état depuis cette seule lecture).

        Idempotent par reco : l'écriture est un upsert sur ``recommendation_id`` (jamais de
        doublon). Si une lettre existe déjà, lève ``LetterExistsError`` **sauf**
        ``overwrite=True`` (choix explicite de l'humain, via le front après un 409) — y
        compris pour écraser une lettre éditée à la main : c'est alors un geste conscient.

        Lève ``UnknownRecommendationError`` si la reco, son offre ou son profil sont
        introuvables (rien n'est généré). Propage ``LLMError`` / ``CoverLetterError`` du
        rédacteur sans les masquer : une génération inexploitable doit être visible.
        """
        decision = self.decisions.get(recommendation_id)
        if decision is None:
            raise UnknownRecommendationError(
                f"recommandation introuvable : {recommendation_id!r}"
            )
        existing = self.letters.get(recommendation_id)
        if existing is not None and not overwrite:
            raise LetterExistsError(
                "une lettre existe déjà pour cette recommandation"
            )
        profile = self.profiles.get(decision.candidate_id)
        offer = self.offers.get(decision.offer_id)
        if profile is None or offer is None:
            raise UnknownRecommendationError(
                "offre ou profil introuvable : impossible de générer la lettre"
            )

        cover = self.redacteur.write_cover_letter(offer, profile)
        now = self._now()
        letter = Letter(
            recommendation_id=recommendation_id,
            body=cover.body,
            source=SOURCE_AI,
            model=cover.model,
            # La date de première création est préservée à la régénération ; seule
            # ``updated_at`` bouge (comme ``created_at`` d'une offre ré-ingérée, OPP-152).
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )
        self.letters.save(letter)
        return letter, existing is None

    def edit(self, recommendation_id: str, body: str) -> Letter:
        """Remplace le corps de la lettre par une version éditée à la main ; ``source=human``.

        Exige une lettre existante (``UnknownLetterError`` sinon) : on édite une lettre,
        on ne la crée pas à blanc par PUT (la génération passe par ``generate``). Lève
        ``LetterError`` si le corps est vide. Préserve ``created_at``, met à jour
        ``updated_at`` et bascule la provenance en ``human`` — ce qui signale au front
        qu'une régénération l'écraserait et mérite confirmation.
        """
        existing = self.letters.get(recommendation_id)
        if existing is None:
            raise UnknownLetterError(
                f"aucune lettre à éditer pour : {recommendation_id!r}"
            )
        if not isinstance(body, str) or body.strip() == "":
            raise LetterError("corps de lettre vide : édition refusée")
        letter = Letter(
            recommendation_id=recommendation_id,
            body=body.strip(),
            source=SOURCE_HUMAN,
            model="",
            created_at=existing.created_at,
            updated_at=self._now(),
        )
        self.letters.save(letter)
        return letter

    def delete(self, recommendation_id: str) -> bool:
        """Supprime la lettre de la reco ; ``True`` si une lettre a été retirée."""
        return self.letters.delete(recommendation_id)
