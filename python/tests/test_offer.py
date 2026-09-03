"""Tests du modèle d'offre standardisée (OPP-037)."""

import pytest

from app.offer import Offer, compute_offer_id
from app.offer_analysis import OfferAnalysis

ANALYSIS = OfferAnalysis(
    title="Développeur Python",
    company="Acme",
    location="  Paris  15e ",
    skills=["Python", "python", "SQL"],
    seniority="Senior",
    contract_type="indépendant",
    summary="Backend data.",
    attention_points=["Astreintes"],
)


def test_compute_offer_id_is_stable_and_deterministic():
    a = compute_offer_id("indeed", "http://x", "Acme", "Dev")
    b = compute_offer_id("  Indeed ", "http://x", "Acme", "  dev ")  # casse/espaces ignorés
    assert a == b


def test_compute_offer_id_stable_across_title_drift_when_url_present():
    # Avec une url, l'id ne dépend que de source+url : le LLM peut reformuler le
    # titre à la ré-analyse sans casser l'upsert.
    assert compute_offer_id("indeed", "http://x", "Acme", "Dev") == compute_offer_id(
        "indeed", "http://x", "Acme", "Développeur Python H/F"
    )


def test_compute_offer_id_disambiguates_by_company_without_url():
    # Sans url, deux offres de même titre mais d'entreprises distinctes ne doivent
    # pas se télescoper (sinon écrasement silencieux).
    assert compute_offer_id("indeed", "", "Acme", "Data Engineer") != compute_offer_id(
        "indeed", "", "Globex", "Data Engineer"
    )


def test_from_analysis_normalizes_and_keeps_provenance():
    offer = Offer.from_analysis(
        ANALYSIS, source="indeed", url="http://x", raw_text="texte brut"
    )
    assert offer.location == "Paris 15e"  # normalisée
    assert offer.skills == ["Python", "SQL"]  # dédoublonnée
    assert offer.contract_type == "Freelance"  # canonicalisée
    assert offer.source == "indeed"
    assert offer.url == "http://x"
    assert offer.raw_text == "texte brut"
    assert offer.id == compute_offer_id("indeed", "http://x", "Acme", "Développeur Python")


def test_from_analysis_requires_source():
    with pytest.raises(ValueError):
        Offer.from_analysis(ANALYSIS, source="  ", raw_text="texte")


def test_from_analysis_requires_raw_text():
    with pytest.raises(ValueError):
        Offer.from_analysis(ANALYSIS, source="indeed", raw_text="")
