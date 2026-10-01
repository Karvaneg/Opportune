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


# --- Type de contrat ---------------------------------------------------------


def test_contract_compatible_cdi():
    assert compare_contract_type(_offer(contract_type="CDI"), _profile(contract_type="CDI")).compatible is True


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
