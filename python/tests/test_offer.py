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
    a = compute_offer_id("indeed", "http://x", "texte de l'offre")
    b = compute_offer_id("  Indeed ", "http://x", "peu importe")  # url présente → texte ignoré
    assert a == b  # casse/espaces de la source ignorés, url seule discrimine


def test_compute_offer_id_stable_across_title_drift_when_url_present():
    # Avec une url, l'id ne dépend que de source+url : le raw_text (et donc toute
    # reformulation LLM en aval) n'entre pas en jeu, l'upsert tient.
    assert compute_offer_id("indeed", "http://x", "texte A") == compute_offer_id(
        "indeed", "http://x", "texte B tout autre"
    )


def test_compute_offer_id_stable_on_same_raw_text_without_url():
    # Le cœur du correctif : sans url, le même texte collé donne le même id — même si
    # le LLM reformule titre/entreprise à la ré-analyse (cause du doublon « Holis »).
    raw = "Développeur Full-Stack chez Holis — ACV, React, PostgreSQL…"
    assert compute_offer_id("collée", "", raw) == compute_offer_id("collée", "", raw)


def test_compute_offer_id_ignores_whitespace_reformatting_of_raw_text():
    # Un simple reformatage du collage (repli de lignes, espaces en trop) ne doit pas
    # fabriquer une offre distincte.
    assert compute_offer_id("collée", "", "Dev Python\n\n  Paris   CDI") == (
        compute_offer_id("collée", "", "  Dev Python Paris CDI  ")
    )


def test_compute_offer_id_dedups_same_url_differing_only_by_tracking():
    # OPP-119 : deux liens vers la même offre ne différant que par des paramètres de
    # tracking (et un slash final) donnent le même id — via la canonicalisation d'URL.
    assert compute_offer_id("indeed", "https://x.com/job/42?utm_source=li", "t A") == (
        compute_offer_id("indeed", "https://x.com/job/42/#apply", "t B autre")
    )


def test_compute_offer_id_disambiguates_distinct_raw_texts_without_url():
    # Sans url, deux textes d'offre réellement différents ne se télescopent pas
    # (sinon écrasement silencieux).
    assert compute_offer_id("collée", "", "Offre A chez Acme") != compute_offer_id(
        "collée", "", "Offre B chez Globex"
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
    assert offer.id == compute_offer_id("indeed", "http://x", "texte brut")


def test_from_analysis_requires_source():
    with pytest.raises(ValueError):
        Offer.from_analysis(ANALYSIS, source="  ", raw_text="texte")


def test_from_analysis_requires_raw_text():
    with pytest.raises(ValueError):
        Offer.from_analysis(ANALYSIS, source="indeed", raw_text="")
