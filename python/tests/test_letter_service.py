"""Tests du service de lettre : génération, édition, suppression (OPP-147).

Aucun réseau : le rédacteur est un stub déterministe, les dépôts sont SQLite en mémoire.
"""

import pytest

from app.candidate_profile import create_profile
from app.cover_letter import CoverLetter
from app.db import connect
from app.decision import create_decision, decision_id
from app.decision_store import DecisionStore
from app.letter import SOURCE_AI, SOURCE_HUMAN, LetterError
from app.letter_service import (
    LetterExistsError,
    LetterService,
    UnknownLetterError,
    UnknownRecommendationError,
)
from app.letter_store import LetterStore
from app.llm_client import LLMError
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore

_VALID_LETTER = (
    "Madame, Monsieur,\n\nVivement intéressée par votre offre, je vous adresse ma "
    "candidature ; mon expérience du backend correspond à vos attentes.\n\n"
    "Cordialement,\nMarie"
)

CAND = "cand-1"
OFF = "off1"
RID = decision_id(CAND, OFF)


class StubRedacteur:
    """Rédacteur déterministe : renvoie une lettre fixe, ou lève une erreur injectée."""

    def __init__(self, *, body=_VALID_LETTER, model="mock-model", raises=None):
        self._body = body
        self._model = model
        self._raises = raises
        self.calls = 0

    def write_cover_letter(self, offer, profile) -> CoverLetter:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return CoverLetter.from_generation(self._body, model=self._model)


def _offer() -> Offer:
    return Offer(
        id=OFF,
        title="Développeuse Python",
        company="Acme",
        location="Paris",
        skills=["Python"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend data.",
        attention_points=[],
        source="collée",
        url="",
        raw_text="Texte brut.",
    )


@pytest.fixture
def ctx():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decisions = DecisionStore(conn)
    letters = LetterStore(conn)
    # Données de base : un profil, une offre, une décision (la reco).
    profiles.save(create_profile(id=CAND, name="Marie", skills=["Python"], contract_type="CDI"))
    offers.save(_offer())
    decisions.save(
        create_decision(
            candidate_id=CAND, offer_id=OFF, action="postuler",
            score=90, justification="Score 90/100.", now=lambda: "t0",
        )
    )
    redacteur = StubRedacteur()
    service = LetterService(
        letters=letters, decisions=decisions, profiles=profiles,
        offers=offers, redacteur=redacteur, now=lambda: "t-gen",
    )
    yield service, redacteur, letters
    conn.close()


def test_generate_creates_ai_letter(ctx):
    service, redacteur, _ = ctx
    letter, created = service.generate(RID)
    assert created is True
    assert letter.source == SOURCE_AI
    assert letter.model == "mock-model"
    assert letter.recommendation_id == RID
    assert redacteur.calls == 1


def test_generate_unknown_recommendation(ctx):
    service, _, _ = ctx
    with pytest.raises(UnknownRecommendationError):
        service.generate("cand-1:inexistante")


def test_generate_twice_without_overwrite_raises(ctx):
    service, redacteur, _ = ctx
    service.generate(RID)
    with pytest.raises(LetterExistsError):
        service.generate(RID)
    # La seconde tentative n'a PAS rappelé le LLM (refus avant génération).
    assert redacteur.calls == 1


def test_generate_overwrite_regenerates(ctx):
    service, redacteur, _ = ctx
    first, first_created = service.generate(RID)
    again, again_created = service.generate(RID, overwrite=True)
    assert first_created is True
    # Régénération : la lettre existait déjà, donc ce n'est pas une création.
    assert again_created is False
    assert redacteur.calls == 2
    # created_at préservé (première ingestion), updated_at identique ici (horloge figée).
    assert again.created_at == first.created_at


def test_generate_overwrite_replaces_human_edit(ctx):
    """Régénérer avec overwrite écrase même une lettre éditée (choix conscient de l'humain)."""
    service, _, _ = ctx
    service.generate(RID)
    service.edit(RID, "Version écrite entièrement à la main par la candidate ici.")
    regenerated, created = service.generate(RID, overwrite=True)
    assert created is False
    assert regenerated.source == SOURCE_AI


def test_generate_propagates_llm_error(ctx):
    service, _, letters = ctx
    service.redacteur = StubRedacteur(raises=LLMError("ollama indisponible"))
    with pytest.raises(LLMError):
        service.generate(RID)
    # Rien n'a été persisté sur échec de génération.
    assert letters.get(RID) is None


def test_edit_sets_human_source_and_preserves_created_at(ctx):
    service, _, _ = ctx
    generated, _ = service.generate(RID)
    edited = service.edit(RID, "  Corps corrigé à la main, bien assez long pour tenir.  ")
    assert edited.source == SOURCE_HUMAN
    assert edited.model == ""
    assert edited.body == "Corps corrigé à la main, bien assez long pour tenir."
    assert edited.created_at == generated.created_at


def test_edit_without_existing_letter_raises(ctx):
    service, _, _ = ctx
    with pytest.raises(UnknownLetterError):
        service.edit(RID, "Un corps de lettre valide et suffisamment long ici.")


def test_edit_empty_body_rejected(ctx):
    service, _, _ = ctx
    service.generate(RID)
    with pytest.raises(LetterError):
        service.edit(RID, "   ")


def test_delete_returns_true_then_false(ctx):
    service, _, _ = ctx
    service.generate(RID)
    assert service.delete(RID) is True
    assert service.get(RID) is None
    assert service.delete(RID) is False
