"""Tests du port Rédacteur et de sa lettre de motivation (OPP-113).

Aucun appel réseau : le LLM est simulé via ``MockLLMClient``.
"""

import pytest

from app.candidate_profile import create_profile
from app.cover_letter import CoverLetter, CoverLetterError
from app.llm_client import LLMError, MockLLMClient
from app.offer import Offer
from app.redacteur import (
    LLMRedacteur,
    Redacteur,
    build_cover_letter_prompt,
)

# Une lettre plausible (assez longue pour passer le garde-fou MIN_BODY_LENGTH).
VALID_LETTER = (
    "Madame, Monsieur,\n\n"
    "Vivement intéressée par votre offre de Développeuse Python, je me permets de "
    "vous adresser ma candidature. Mon expérience du backend et ma rigueur "
    "correspondent aux compétences que vous recherchez.\n\n"
    "Je serais ravie d'échanger avec vous.\n\nCordialement,\nMarie"
)


def _offer(**overrides) -> Offer:
    data = dict(
        id="off1",
        title="Développeuse Python",
        company="Acme",
        location="Paris",
        skills=["Python", "SQL"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend data au sein d'une équipe produit.",
        attention_points=["Astreintes"],
        source="collée",
        url="",
        raw_text="Texte brut de l'offre.",
    )
    data.update(overrides)
    return Offer(**data)


def _profile(**overrides):
    data = dict(
        name="Marie",
        skills=["Python", "SQL"],
        contract_type="CDI",
        experiences=[{"poste": "Dev backend", "entreprise": "Foo", "duree": "3 ans"}],
        languages=["Français", "Anglais"],
        location="Rennes",
    )
    data.update(overrides)
    return create_profile(**data)


# --- Prompt ------------------------------------------------------------------


def test_prompt_is_deterministic():
    offer, profile = _offer(), _profile()
    assert build_cover_letter_prompt(offer, profile) == build_cover_letter_prompt(
        offer, profile
    )


def test_prompt_contains_offer_and_profile_data():
    prompt = build_cover_letter_prompt(_offer(), _profile())
    # Données de l'offre.
    assert "Développeuse Python" in prompt
    assert "Acme" in prompt
    assert "Astreintes" in prompt
    # Données du profil.
    assert "Marie" in prompt
    assert "Anglais" in prompt
    assert "Dev backend" in prompt  # expérience (objet) rendue


def test_prompt_omits_absent_optional_fields():
    # Un profil minimal ne doit pas produire de lignes « None » parasites.
    prompt = build_cover_letter_prompt(_offer(), _profile(languages=[], location=None))
    assert "None" not in prompt
    assert "Langues" not in prompt


# --- CoverLetter (validation) ------------------------------------------------


def test_cover_letter_from_generation_trims_and_keeps_metadata():
    letter = CoverLetter.from_generation(
        "  " + VALID_LETTER + "  ", model="ministral", raw={"k": "v"}
    )
    assert isinstance(letter, CoverLetter)
    assert letter.body == VALID_LETTER.strip()
    assert letter.model == "ministral"
    assert letter.raw == {"k": "v"}


def test_cover_letter_rejects_empty():
    with pytest.raises(CoverLetterError):
        CoverLetter.from_generation("   ", model="ministral")


def test_cover_letter_rejects_too_short():
    with pytest.raises(CoverLetterError):
        CoverLetter.from_generation("Trop court.", model="ministral")


def test_cover_letter_rejects_refusal_even_when_long_enough():
    # Un refus poli dépasse MIN_BODY_LENGTH : la longueur seule ne suffit pas à le
    # rattraper, le préfixe de refus doit le faire.
    refusal = (
        "Je ne peux pas rédiger cette lettre de motivation car je n'ai pas "
        "suffisamment d'informations sur votre profil pour produire un contenu "
        "pertinent et sincère."
    )
    assert len(refusal) >= 100  # garde-fou de longueur inopérant ici
    with pytest.raises(CoverLetterError):
        CoverLetter.from_generation(refusal, model="ministral")


# --- LLMRedacteur ------------------------------------------------------------


def test_write_cover_letter_returns_structured_result():
    client = MockLLMClient([VALID_LETTER])
    letter = LLMRedacteur(client).write_cover_letter(_offer(), _profile())

    assert isinstance(letter, CoverLetter)
    assert letter.body == VALID_LETTER
    # Le prompt réellement envoyé au LLM porte les données de l'offre et du profil.
    assert "Développeuse Python" in client.calls[0]["prompt"]
    assert "Marie" in client.calls[0]["prompt"]


def test_write_cover_letter_rejects_unusable_generation():
    client = MockLLMClient(["N/A"])  # génération trop courte
    with pytest.raises(CoverLetterError):
        LLMRedacteur(client).write_cover_letter(_offer(), _profile())


def test_write_cover_letter_propagates_llm_error():
    client = MockLLMClient(error=LLMError("réseau"))
    with pytest.raises(LLMError):
        LLMRedacteur(client).write_cover_letter(_offer(), _profile())


def test_llm_redacteur_satisfies_port():
    assert isinstance(LLMRedacteur(MockLLMClient()), Redacteur)
