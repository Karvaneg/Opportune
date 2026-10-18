"""Tests du matching profil ↔ offre (OPP-038).

Comparaison déterministe, sans LLM ni réseau : on construit des `Offer` et
`CandidateProfile` en mémoire.
"""

from app.candidate_profile import create_profile
from app.offer import Offer
from app.offer_profile_match import (
    compare_contract_type,
    compare_location,
    compare_seniority,
    compare_skills,
    match_offer_to_profile,
)


def _offer(**overrides) -> Offer:
    data = dict(
        id="o-1",
        title="Développeur Python",
        company="Acme",
        location="Paris",
        skills=["Python", "SQL"],
        seniority="Senior",
        contract_type="CDI",
        summary="Backend.",
        attention_points=[],
        source="indeed",
        url="http://x",
        raw_text="texte",
    )
    data.update(overrides)
    return Offer(**data)


def _profile(**overrides):
    data = dict(name="Marie", skills=["Python"], contract_type="CDI")
    data.update(overrides)
    return create_profile(**data)


# --- Compétences -------------------------------------------------------------


def test_skills_matched_and_missing_case_insensitive():
    offer = _offer(skills=["Python", "SQL", "Go"])
    profile = _profile(skills=["python", "sql"])
    result = compare_skills(offer, profile)
    assert result.matched == ["Python", "SQL"]  # libellés de l'offre conservés
    assert result.missing == ["Go"]


def test_skills_matched_via_alias_and_family():
    # Scénario Holis (OPP-139) : l'offre exige JavaScript et PostgreSQL ; le profil ne
    # les nomme pas littéralement mais couvre les deux (React⇒JavaScript, alias Postgres).
    offer = _offer(skills=["JavaScript", "PostgreSQL", "Rust"])
    profile = _profile(skills=["React", "TypeScript", "Postgres"])
    result = compare_skills(offer, profile)
    assert result.matched == ["JavaScript", "PostgreSQL"]  # plus de faux négatif
    assert result.missing == ["Rust"]  # réellement absent → toujours manquant


def test_skills_unspecified_sentinel_is_ignored():
    # OPP-151 : « Non précisé » glissé dans la liste de compétences = absence, pas une
    # compétence exigée → ni matched ni missing (ne pénalise pas une offre éparse).
    offer = _offer(skills=["Python", "Non précisé"])
    profile = _profile(skills=["Python"])
    result = compare_skills(offer, profile)
    assert result.matched == ["Python"]
    assert result.missing == []


def test_skills_extraction_noise_is_dropped():
    # OPP-157 : le bruit d'extraction (« etc. », normes) ne gonfle plus le dénominateur,
    # même sur une offre déjà persistée (filtrage au moment de comparer).
    offer = _offer(skills=["Python", "etc.", "ISO", "Go"])
    profile = _profile(skills=["python"])
    result = compare_skills(offer, profile)
    assert result.matched == ["Python"]
    assert result.missing == ["Go"]  # « etc. » et « ISO » retirés, pas comptés manquants


def test_skills_quasi_duplicates_counted_once():
    # OPP-157 : « REST API » et « RESTful Design » partagent la même forme canonique → une
    # seule entrée manquante, pas deux (sinon pénalité double pour un seul concept).
    offer = _offer(skills=["REST API", "RESTful Design", "Python"])
    profile = _profile(skills=["python"])
    result = compare_skills(offer, profile)
    assert result.matched == ["Python"]
    assert result.missing == ["REST API"]  # le second quasi-doublon est absorbé


def test_skills_ci_cd_matched_via_pipeline_family():
    # OPP-157 : une offre exigeant « CI/CD » est couverte par un profil « GitHub Actions ».
    offer = _offer(skills=["CI/CD"])
    profile = _profile(skills=["GitHub Actions"])
    result = compare_skills(offer, profile)
    assert result.matched == ["CI/CD"]
    assert result.missing == []


# --- Type de contrat ---------------------------------------------------------


def test_contract_compatible_cdi():
    assert compare_contract_type(_offer(contract_type="CDI"), _profile(contract_type="CDI")).compatible is True


def test_contract_compound_label_recognised_as_cdi():
    # OPP-156 : « CDI (permanent) » (libellé composé déjà persisté) reste reconnu comme CDI au
    # moment de comparer, sans ré-ingestion. Le libellé d'origine est conservé à l'affichage.
    result = compare_contract_type(
        _offer(contract_type="CDI (permanent)"), _profile(contract_type="CDI")
    )
    assert result.compatible is True
    assert result.offer == "CDI (permanent)"


def test_contract_incompatible():
    result = compare_contract_type(_offer(contract_type="Freelance"), _profile(contract_type="CDI"))
    assert result.compatible is False


def test_contract_les_deux_accepts_freelance():
    result = compare_contract_type(_offer(contract_type="Freelance"), _profile(contract_type="les deux"))
    assert result.compatible is True


def test_contract_les_deux_rejects_cdd():
    # « les deux » = CDI ou freelance : un CDD n'est visé par aucune préférence.
    result = compare_contract_type(_offer(contract_type="CDD"), _profile(contract_type="les deux"))
    assert result.compatible is False


def test_contract_none_when_offer_side_absent():
    result = compare_contract_type(_offer(contract_type=""), _profile(contract_type="CDI"))
    assert result.compatible is None


def test_contract_unspecified_sentinel_is_not_a_mismatch():
    # OPP-151 : « Non précisé » (défaut LLM) = absence, pas un contrat incompatible.
    result = compare_contract_type(_offer(contract_type="Non précisé"), _profile(contract_type="CDI"))
    assert result.compatible is None


# --- Localisation ------------------------------------------------------------


def test_location_match_substring():
    result = compare_location(_offer(location="Paris"), _profile(location="Paris 15e"))
    assert result.status == "match"


def test_location_mismatch():
    result = compare_location(_offer(location="Lyon"), _profile(location="Paris"))
    assert result.status == "mismatch"


def test_location_not_blocking_when_profile_mobile():
    result = compare_location(
        _offer(location="Lyon"), _profile(location="Paris", mobility="France entière")
    )
    assert result.status == "not_blocking"
    assert result.reason == "profile-mobility"


def test_location_negated_mobility_does_not_rescue_mismatch():
    # « non mobile » ne doit PAS requalifier un écart en not_blocking (point de revue).
    result = compare_location(
        _offer(location="Lyon"), _profile(location="Paris", mobility="non mobile")
    )
    assert result.status == "mismatch"


def test_location_unknown_when_profile_missing():
    result = compare_location(_offer(location="Lyon"), _profile())  # profil sans location
    assert result.status == "unknown"


def test_location_unspecified_sentinel_is_unknown_not_mismatch():
    # OPP-151 : offre « Non précisé » en lieu = absence → non évaluable, pas un écart.
    result = compare_location(_offer(location="Non précisé"), _profile(location="Paris"))
    assert result.status == "unknown"


def test_location_not_blocking_when_offer_is_remote():
    # OPP-140 : offre en télétravail → écart de lieu non bloquant, même profil non mobile.
    result = compare_location(
        _offer(location="Paris (BnF, M6) - Télétravail possible"),
        _profile(location="Gironde"),
    )
    assert result.status == "not_blocking"
    assert result.reason == "offer-remote"


def test_location_remote_detected_outside_location_field():
    # Revue OPP-140 : le télétravail est souvent hors du champ lieu (ici dans le summary).
    result = compare_location(
        _offer(location="Lyon", summary="Poste full remote, équipe distribuée."),
        _profile(location="Paris"),
    )
    assert result.status == "not_blocking"
    assert result.reason == "offer-remote"


def test_location_remote_contradicted_by_onsite_is_mismatch():
    # OPP-162 : « télétravail possible MAIS présentiel / en laboratoire obligatoire » ne doit
    # pas être crédité comme remote — l'écart de lieu reste bloquant.
    result = compare_location(
        _offer(
            location="Guidel (56) – Présentiel (télétravail complet possible mais "
            "validation en laboratoire obligatoire)"
        ),
        _profile(location="Gironde"),
    )
    assert result.status == "mismatch"


# --- Séniorité / expérience --------------------------------------------------


def test_seniority_ok_when_enough_experience():
    result = compare_seniority(_offer(seniority="Senior"), _profile(total_experience_years=6))
    assert result.required_years == 5
    assert result.status == "ok"


def test_seniority_insufficient():
    result = compare_seniority(_offer(seniority="Senior"), _profile(total_experience_years=2))
    assert result.status == "insufficient"


def test_seniority_unknown_when_profile_missing_years():
    result = compare_seniority(_offer(seniority="Senior"), _profile())
    assert result.status == "unknown"


def test_seniority_unknown_when_label_unrecognized():
    result = compare_seniority(_offer(seniority="Ninja"), _profile(total_experience_years=6))
    assert result.status == "unknown"


def test_seniority_not_required_when_unspecified():
    result = compare_seniority(_offer(seniority="Non précisé"), _profile(total_experience_years=6))
    assert result.status == "not_required"


def test_seniority_explicit_years_override_level_mapping():
    # OPP-162 : « Confirmé (5 ans minimum) » valait 3 (via « confirmé ») ; le nombre explicite
    # doit primer → 5 requis, donc 2 ans = insuffisant (et non « ok » contre 3).
    result = compare_seniority(
        _offer(seniority="Confirmé (5 ans d'expérience minimum)"),
        _profile(total_experience_years=2),
    )
    assert result.required_years == 5
    assert result.status == "insufficient"


def test_seniority_explicit_years_range_takes_lowest():
    # « 3 à 5 ans » → on exige dès le seuil le plus bas (3).
    result = compare_seniority(
        _offer(seniority="3 à 5 ans d'expérience"), _profile(total_experience_years=4)
    )
    assert result.required_years == 3
    assert result.status == "ok"


def test_seniority_range_takes_lowest_level():
    # OPP-140 : « Junior à Confirmé » → seuil le plus bas (junior=0). 2 ans suffisent.
    result = compare_seniority(
        _offer(seniority="Junior à Confirmé"), _profile(total_experience_years=2)
    )
    assert result.required_years == 0
    assert result.status == "ok"


def test_seniority_range_insufficient_below_lowest():
    # « Senior à Lead » → min(5, 8) = 5 ; 2 ans < 5 → insuffisant.
    result = compare_seniority(
        _offer(seniority="Senior à Lead"), _profile(total_experience_years=2)
    )
    assert result.required_years == 5
    assert result.status == "insufficient"


def test_seniority_range_with_slash_separator():
    result = compare_seniority(
        _offer(seniority="Confirmé/Senior"), _profile(total_experience_years=4)
    )
    assert result.required_years == 3  # min(confirmé=3, senior=5)
    assert result.status == "ok"


def test_seniority_exclusion_is_not_permissive():
    # Revue OPP-140 : une exclusion (« débutants s'abstenir ») ne doit pas être lue comme
    # un seuil bas permissif → non évaluable plutôt que « ok » pour 2 ans.
    result = compare_seniority(
        _offer(seniority="Senior, débutants s'abstenir"),
        _profile(total_experience_years=2),
    )
    assert result.status == "unknown"


def test_seniority_negation_of_level_falls_back_to_unknown():
    result = compare_seniority(
        _offer(seniority="Confirmé, pas de junior"), _profile(total_experience_years=1)
    )
    assert result.status == "unknown"  # ne pas créditer via le « junior » nié


# --- Point d'entrée ----------------------------------------------------------


def test_match_offer_to_profile_aggregates_all_dimensions():
    result = match_offer_to_profile(
        _offer(), _profile(skills=["Python"], total_experience_years=6, location="Paris")
    )
    assert result.skills.matched == ["Python"]
    assert result.skills.missing == ["SQL"]
    assert result.contract_type.compatible is True
    assert result.location.status == "match"
    assert result.seniority.status == "ok"
