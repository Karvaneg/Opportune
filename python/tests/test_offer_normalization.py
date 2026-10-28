"""Tests de la normalisation déterministe des champs d'offre (OPP-037)."""

from app.offer_normalization import (
    drop_non_skills,
    drop_unanchored_skills,
    normalize_contract,
    normalize_location,
    normalize_skills,
)


def test_contract_canonicalises_known_synonyms():
    assert normalize_contract("CDI") == "CDI"
    assert normalize_contract("  cdi ") == "CDI"
    assert normalize_contract("Indépendant") == "Freelance"
    assert normalize_contract("mission") == "Freelance"
    assert normalize_contract("Apprentissage") == "Alternance"


def test_contract_keeps_unknown_value_cleaned():
    assert normalize_contract("  Portage   salarial ") == "Portage salarial"


def test_contract_canonicalises_compound_labels():
    # Libellés composés produits par le LLM (OPP-156) : un synonyme non ambigu à l'intérieur
    # suffit à retrouver la forme canonique.
    assert normalize_contract("CDI (permanent)") == "CDI"
    assert normalize_contract("CDI - temps plein") == "CDI"
    assert normalize_contract("Contrat CDD, 6 mois") == "CDD"


def test_contract_ambiguous_compound_stays_cleaned():
    # Deux formes canoniques en conflit → on n'invente pas, on conserve le libellé nettoyé.
    assert normalize_contract("CDD puis CDI") == "CDD puis CDI"


def test_contract_weak_synonym_not_matched_inside_compound():
    # « mission »/« consultant » sont trop génériques pour réécrire un libellé composé : on ne
    # les reconnaît qu'en lookup direct, pas noyés dans une phrase (sinon on freelanciserait à
    # tort des libellés entiers). Exact → canonicalisé ; composé → conservé.
    assert normalize_contract("Mission") == "Freelance"
    assert normalize_contract("Mission d'intérêt général") == "Mission d'intérêt général"
    assert normalize_contract("Consultant junior en CDI") == "CDI"


def test_location_collapses_whitespace():
    assert normalize_location("  Paris   15e  ") == "Paris 15e"


def test_skills_dedupe_case_insensitive_keep_order():
    assert normalize_skills(["Python", "python", "SQL", "  Python  "]) == ["Python", "SQL"]


def test_skills_drop_empty_entries():
    assert normalize_skills(["  ", "Docker", ""]) == ["Docker"]


def test_skills_atomize_parenthesised_enumeration():
    # « Back-end (PostgreSQL, Express) » doit être éclaté en éléments atomiques.
    assert normalize_skills(["Back-end (PostgreSQL, Express)"]) == [
        "Back-end",
        "PostgreSQL",
        "Express",
    ]


def test_skills_atomize_slash_group():
    assert normalize_skills(["HTML/CSS/JS"]) == ["HTML", "CSS", "JS"]


def test_skills_keep_atomic_slash_acronyms_whole():
    # CI/CD, TCP/IP… sont atomiques : ne pas les éclater sur le « / ».
    assert normalize_skills(["CI/CD", "TCP/IP"]) == ["CI/CD", "TCP/IP"]


def test_skills_atomize_then_dedupe_across_entries():
    # Éclatement puis dédoublonnage casse-insensible entre entrées distinctes.
    assert normalize_skills(["React, Node", "node", "React"]) == ["React", "Node"]


# --- drop_non_skills (OPP-142) ----------------------------------------------


def test_drop_non_skills_removes_norms_and_organisms():
    # Normes/labels et organismes/partenaires ne sont pas des compétences.
    assert drop_non_skills(["Python", "ISO", "UNESCO", "WCAG", "ADEME", "Docker"]) == [
        "Python",
        "Docker",
    ]


def test_drop_non_skills_removes_task_formulations():
    # Tâches formulées en verbe : « ActionNoun de/des … » → pas une techno.
    assert drop_non_skills(
        [
            "Optimisation de calculs",
            "Gestion des droits utilisateurs",
            "Conception de tableaux de bord",
            "Parsing de documents",
            "Traitement de données hétérogènes",
            "React",
        ]
    ) == ["React"]


def test_drop_non_skills_conservative_keeps_real_skills():
    # Conservateur : « Microsoft » seul tombe, mais les vraies technos restent
    # (dont un multi-mots légitime avec « de » qui n'est pas une tâche).
    kept = ["Microsoft Azure", "base de données", "Node.js", "React Native", "CI/CD"]
    assert drop_non_skills(["Microsoft", *kept]) == kept


def test_drop_non_skills_keeps_recognized_competencies():
    # Conservateur, suite : ni « Analyse … » (préfixe trop générique retiré) ni les
    # compléments métier (« … de projet/système/logiciel ») ne sont du bruit — ce
    # sont des compétences reconnues, à distinguer des vraies tâches filtrées.
    kept = [
        "Analyse de données",
        "Analyse de risques",
        "Gestion de projet",
        "Conception de systèmes",
        "Développement de logiciels",
    ]
    assert drop_non_skills([*kept, "Optimisation de calculs"]) == kept


def test_drop_non_skills_preserves_order_and_case():
    assert drop_non_skills(["PostgreSQL", "iso", "GraphQL"]) == ["PostgreSQL", "GraphQL"]


def test_drop_non_skills_removes_enumeration_filler():
    # OPP-157 : le petit LLM clôt souvent une énumération par « etc. » / « … ».
    assert drop_non_skills(["React", "etc.", "Node.js", "...", "…"]) == ["React", "Node.js"]


def test_drop_non_skills_removes_bare_numbers_but_keeps_versioned_techs():
    # OPP-213 : un nombre ou numéro de version orphelin (« 3 », « 8.1 », « 2024 ») détaché
    # par le modèle n'est pas une compétence ; une techno versionnée (lettre présente) survit.
    assert drop_non_skills(
        ["PHP", "Symfony", "3", "Symfony 6.4", "8.1", "2024", "C++", "C#", ".NET", "3D"]
    ) == ["PHP", "Symfony", "Symfony 6.4", "C++", "C#", ".NET", "3D"]


# --- Ancrage au texte réel (OPP-213) ----------------------------------------


def test_drop_unanchored_keeps_only_skills_present_in_text():
    # Cas réel observé : le modèle invente une stack plausible à partir d'un titre.
    text = "Lead Développeur React.js — agence digitale spécialisée en React."
    skills = ["React.js", "JavaScript", "AWS", "Docker"]
    assert drop_unanchored_skills(skills, text) == ["React.js"]


def test_drop_unanchored_is_accent_and_case_insensitive():
    # « Développé en PYTHON » doit ancrer « Python » malgré casse et accents alentour.
    assert drop_unanchored_skills(["Python"], "Projet développé en PYTHON") == ["Python"]


def test_drop_unanchored_tolerates_surrounding_punctuation():
    # Node.js suivi d'une ponctuation dans l'annonce reste ancré (la ponctuation est
    # réduite à un séparateur des deux côtés).
    assert drop_unanchored_skills(["Node.js"], "Stack : Node.js, Express.") == ["Node.js"]


def test_drop_unanchored_requires_word_boundary():
    # Un token court ne doit pas matcher l'intérieur d'un autre mot (« Go » dans « Google »).
    assert drop_unanchored_skills(["Go"], "Nous utilisons Google Workspace") == []


def test_drop_unanchored_empty_when_text_has_no_skill():
    # Laïus corporate sans techno : aucune compétence ancrée → liste vide (et non inventée).
    text = "Agence internationale dédiée à l'expérience digitale et au Commerce Omnicanal."
    assert drop_unanchored_skills(["Python", "AWS", "Docker"], text) == []


def test_drop_unanchored_preserves_order_and_original_casing():
    text = "Compétences : python, react, sql"
    assert drop_unanchored_skills(["React", "SQL", "Python"], text) == ["React", "SQL", "Python"]
