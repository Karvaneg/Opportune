"""Tests de la classification du type d'offre (OPP-166).

Déterministe, sans LLM : on vérifie que l'heuristique sépare une formation (marqueurs
explicites) d'une offre d'emploi ordinaire, et que ``resolve_kind`` combine LLM + filet.
"""

from app.offer_kind import (
    DEFAULT_KIND,
    EMPLOI,
    FORMATION,
    classify_kind,
    resolve_kind,
)

# Extrait fidèle de l'offre réelle qui a motivé le ticket (POE ISTQB, base de dogfood) :
# titre trompeur (ressemble à un poste) mais corps sans ambiguïté — une formation.
ISTQB_TITLE = "Ingénieur.e Test Logiciel certifié.e ISTQB"
ISTQB_TEXT = (
    "Devenez Ingénieur.e Test logiciel certifié.e ISTQB. 64 jours (448 heures). "
    "Dispositif : Préparation Opérationnelle à l'Emploi (POE). "
    "Nous vous proposons d'intégrer un programme de formation éligible au financement."
)


def test_default_kind_is_emploi():
    assert DEFAULT_KIND == EMPLOI


def test_plain_job_offer_is_emploi():
    assert classify_kind("Développeur Python Senior", "CDI, Python, PostgreSQL.") == EMPLOI


def test_job_mentioning_training_perk_stays_emploi():
    # Un seul marqueur faible (« formation continue ») ne suffit pas à basculer un emploi.
    text = "CDI. Nous offrons de la formation continue et un budget conférences."
    assert classify_kind("Développeur Full-Stack", text) == EMPLOI


def test_title_marker_alone_is_formation():
    assert classify_kind("Formation Développeur Web", "Apprenez le métier.") == FORMATION


def test_bootcamp_title_is_formation():
    assert classify_kind("Bootcamp Data Analyst", "Douze semaines intensives.") == FORMATION


def test_structural_markers_make_formation_despite_jobbish_title():
    # Le cas ISTQB : titre qui ressemble à un poste, mais le corps accumule les marqueurs.
    assert classify_kind(ISTQB_TITLE, ISTQB_TEXT) == FORMATION


def test_accents_and_case_are_ignored():
    assert classify_kind("FORMATION Diplômante", "Cursus certifiant.") == FORMATION


def test_poe_matched_as_word_not_substring():
    # « poêle » (normalisé « poele ») ne doit pas déclencher le marqueur « poe ».
    assert classify_kind("Vendeur poêles à bois", "Magasin de poêles.") == EMPLOI


def test_resolve_kind_heuristic_overrides_llm_emploi_for_formation():
    # Le LLM se trompe (emploi) mais les marqueurs explicites priment → formation.
    assert resolve_kind("emploi", ISTQB_TITLE, ISTQB_TEXT) == FORMATION


def test_resolve_kind_trusts_llm_when_heuristic_silent():
    assert resolve_kind("formation", "Chef de projet", "Pilotage d'équipe.") == FORMATION


def test_resolve_kind_falls_back_to_emploi_on_unknown_or_missing():
    assert resolve_kind(None, "Développeur", "CDI.") == EMPLOI
    assert resolve_kind("n'importe quoi", "Développeur", "CDI.") == EMPLOI
