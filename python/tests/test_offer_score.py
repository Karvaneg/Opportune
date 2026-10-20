"""Tests du scoring explicable de l'adéquation offre ↔ profil (OPP-039).

Déterministe, sans LLM ni réseau. On construit des `OfferProfileMatch` directement
pour isoler la logique de scoring, et on couvre aussi les raccourcis de bout en bout.
"""

from app.candidate_profile import create_profile
from app.offer import Offer
from app.offer_profile_match import (
    ContractMatch,
    LocationMatch,
    OfferProfileMatch,
    SeniorityMatch,
    SkillMatch,
)
from app.offer_score import (
    SKILL_UNKNOWN_SCORE_CAP,
    explain_offer_to_profile,
    explain_score,
    score_match,
    score_offer_to_profile,
)


def _match(**overrides) -> OfferProfileMatch:
    data = dict(
        skills=SkillMatch(matched=["Python"], missing=[]),
        contract_type=ContractMatch(offer="CDI", profile="CDI", compatible=True),
        location=LocationMatch(offer="Paris", profile="Paris", status="match"),
        seniority=SeniorityMatch(offer_label="Senior", required_years=5, profile_years=6, status="ok"),
    )
    data.update(overrides)
    return OfferProfileMatch(**data)


# --- Score -------------------------------------------------------------------


def test_perfect_match_scores_100():
    assert score_match(_match()).score == 100


def test_all_unfavorable_scores_0():
    # Tout défavorable, séniorité comprise : 0 an d'expérience face à une exigence → ratio 0.
    match = _match(
        skills=SkillMatch(matched=[], missing=["Go"]),
        contract_type=ContractMatch(offer="Freelance", profile="CDI", compatible=False),
        location=LocationMatch(offer="Lyon", profile="Paris", status="mismatch"),
        seniority=SeniorityMatch(offer_label="Senior", required_years=5, profile_years=0, status="insufficient"),
    )
    assert score_match(match).score == 0


def test_insufficient_seniority_is_graduated_not_zeroed():
    # Near-miss (OPP-156) : 2 ans face à 5 requis → ratio 0.4 sur la dimension séniorité (poids
    # 0.15) → 6/100, au lieu d'un 0 sec. Seule la séniorité est évaluable ici (autres inconnues).
    match = _match(
        skills=SkillMatch(matched=[], missing=[]),  # total 0 → non évaluable
        contract_type=ContractMatch(offer=None, profile=None, compatible=None),
        location=LocationMatch(offer=None, profile=None, status="unknown"),
        seniority=SeniorityMatch(offer_label="Senior", required_years=5, profile_years=2, status="insufficient"),
    )
    result = score_match(match)
    # Séniorité seule évaluable → score = sous-score séniorité renormalisé = 0.4 → 40.
    assert result.score == 40
    assert result.breakdown["seniority"].value == 0.4


def test_unknown_dimension_is_excluded_not_zeroed():
    # Contrat compatible + skills parfait, mais séniorité et lieu inconnus :
    # le score doit rester 100 (dimensions inconnues exclues, pas comptées 0).
    match = _match(
        seniority=SeniorityMatch(offer_label="Ninja", required_years=None, profile_years=None, status="unknown"),
        location=LocationMatch(offer=None, profile=None, status="unknown"),
    )
    result = score_match(match)
    assert result.score == 100
    assert result.breakdown["seniority"].evaluated is False
    assert result.breakdown["location"].evaluated is False
    assert result.breakdown["skills"].evaluated is True


def test_partial_skill_coverage_weighted():
    # skills 0.5 (1/2), contrat 1, séniorité 1, lieu 1.
    # score = (0.5*0.45 + 1*0.30 + 1*0.15 + 1*0.10) / 1.0 = 0.775 → 78
    match = _match(skills=SkillMatch(matched=["Python"], missing=["Go"]))
    assert score_match(match).score == 78


def test_low_skill_coverage_gates_whole_score():
    # OPP-162 : couverture compétences très faible (1/10 = 0.1) → facteur 0.1/0.5 = 0.2 appliqué
    # au score. Sans garde-fou, contrat+séniorité+lieu maintiendraient un score élevé malgré
    # une offre d'un autre métier.
    missing = [f"skill{i}" for i in range(9)]
    match = _match(skills=SkillMatch(matched=["Python"], missing=missing))
    # base = (0.1*0.45 + 1*0.30 + 1*0.15 + 1*0.10) / 1.0 = 0.595 ; ×0.2 = 0.119 → 12.
    assert score_match(match).score == 12


def test_low_skill_coverage_adds_a_reason():
    match = _match(skills=SkillMatch(matched=["Python"], missing=[f"s{i}" for i in range(9)]))
    negatives = explain_score(match).negatives
    assert any("hors de ton métier" in r.message for r in negatives)


def test_unevaluable_skills_cap_the_score():
    # OPP-168 : compétences non listées (total 0) → la dimension déterminante (0.45) est un angle
    # mort. Contrat/séniorité/lieu tous à 1 donneraient 100 ; le plafond de confiance borne à 40.
    match = _match(skills=SkillMatch(matched=[], missing=[]))
    assert score_match(match).score == SKILL_UNKNOWN_SCORE_CAP


def test_unevaluable_skills_cap_from_handoff_case():
    # Cas réel du handoff OPP-167 : offre Adzuna sans compétences, CDI compatible, lieu différent,
    # séniorité non exigée → base 0.75 (flottait à 75). Plafonnée à 40.
    match = _match(
        skills=SkillMatch(matched=[], missing=[]),
        contract_type=ContractMatch(offer="CDI", profile="CDI", compatible=True),
        location=LocationMatch(offer="Lyon", profile="Paris", status="mismatch"),
        seniority=SeniorityMatch(offer_label=None, required_years=None, profile_years=6, status="not_required"),
    )
    assert score_match(match).score == SKILL_UNKNOWN_SCORE_CAP


def test_unevaluable_skills_cap_adds_a_reason():
    match = _match(skills=SkillMatch(matched=[], missing=[]))
    negatives = explain_score(match).negatives
    assert any("plafonné par prudence" in r.message for r in negatives)


def test_unevaluable_skills_below_cap_left_untouched():
    # Score déjà sous le plafond → le plafond ne mord pas, et aucune raison « plafonné » n'est
    # ajoutée (OPP-168 : on ne prétend pas plafonner ce qui ne l'a pas été).
    match = _match(
        skills=SkillMatch(matched=[], missing=[]),
        contract_type=ContractMatch(offer="Freelance", profile="CDI", compatible=False),
        location=LocationMatch(offer="Lyon", profile="Paris", status="mismatch"),
        seniority=SeniorityMatch(offer_label=None, required_years=None, profile_years=6, status="not_required"),
    )
    # Seuls contrat (0) et lieu (0) évaluables → base 0 → score 0, inchangé.
    assert score_match(match).score == 0
    assert not any("plafonné par prudence" in r.message for r in explain_score(match).negatives)


def test_good_skill_coverage_is_not_penalized():
    # Couverture ≥ genou (0.5) → facteur 1, aucun effet : 3/4 = 0.75.
    match = _match(skills=SkillMatch(matched=["a", "b", "c"], missing=["d"]))
    # base = (0.75*0.45 + 1*0.30 + 1*0.15 + 1*0.10) = 0.8875 → 89, sans réduction.
    assert score_match(match).score == 89


def test_no_evaluable_dimension_scores_none():
    # Aucune dimension mesurable → score None (« non évaluable »), à distinguer d'un 0
    # (adéquation nulle mais mesurée).
    match = OfferProfileMatch(
        skills=SkillMatch(matched=[], missing=[]),
        contract_type=ContractMatch(offer=None, profile=None, compatible=None),
        location=LocationMatch(offer=None, profile=None, status="unknown"),
        seniority=SeniorityMatch(offer_label=None, required_years=None, profile_years=None, status="not_required"),
    )
    result = score_match(match)
    assert result.score is None
    assert all(not d.evaluated for d in result.breakdown.values())


# --- Explication -------------------------------------------------------------


def test_explain_sorts_reasons_by_weight():
    match = _match(
        skills=SkillMatch(matched=[], missing=["Go"]),  # negative, weight 0.45
        location=LocationMatch(offer="Lyon", profile="Paris", status="mismatch"),  # negative, 0.10
        contract_type=ContractMatch(offer="Freelance", profile="CDI", compatible=False),  # negative, 0.30
    )
    explanation = explain_score(match)
    weights = [r.weight for r in explanation.negatives]
    assert weights == sorted(weights, reverse=True)  # tri décroissant
    assert explanation.negatives[0].dimension == "skills"


def test_explain_separates_impacts():
    match = _match(
        skills=SkillMatch(matched=["Python"], missing=["Go"]),  # 1 positive + 1 negative
        seniority=SeniorityMatch(offer_label="Ninja", required_years=None, profile_years=None, status="unknown"),
    )
    explanation = explain_score(match)
    assert any(r.dimension == "skills" and r.impact == "positive" for r in explanation.positives)
    assert any(r.dimension == "skills" and r.impact == "negative" for r in explanation.negatives)
    assert any(r.dimension == "seniority" and r.impact == "unknown" for r in explanation.unknown)


def test_seniority_reason_formats_float_years_without_decimal():
    match = _match(
        seniority=SeniorityMatch(offer_label="Senior", required_years=5, profile_years=6.0, status="ok")
    )
    message = next(r.message for r in explain_score(match).positives if r.dimension == "seniority")
    assert "6 ans" in message  # 6.0 → « 6 », pas « 6.0 »


def test_not_required_seniority_yields_no_reason():
    match = _match(
        seniority=SeniorityMatch(offer_label="Non précisé", required_years=None, profile_years=6, status="not_required")
    )
    explanation = explain_score(match)
    assert all(r.dimension != "seniority" for r in explanation.positives + explanation.negatives + explanation.unknown)


# --- Raccourcis de bout en bout ----------------------------------------------


def _offer(**overrides) -> Offer:
    data = dict(
        id="o-1", title="Dev", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="Backend.", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


def test_score_and_explain_offer_to_profile_end_to_end():
    offer = _offer()
    profile = create_profile(name="Marie", skills=["Python", "SQL"], contract_type="CDI",
                             location="Paris", total_experience_years=6)
    assert score_offer_to_profile(offer, profile).score == 100
    explanation = explain_offer_to_profile(offer, profile)
    assert explanation.score == 100
    assert explanation.positives  # au moins une raison positive


def test_formation_is_not_scored():
    # OPP-166 : une formation n'est pas évaluée sur l'adéquation des compétences (son but est
    # de les acquérir). Score None (jamais 0), aucune raison — même avec un profil parfait.
    offer = _offer(kind="formation")
    profile = create_profile(name="Marie", skills=["Python", "SQL"], contract_type="CDI",
                             location="Paris", total_experience_years=6)
    assert score_offer_to_profile(offer, profile).score is None
    explanation = explain_offer_to_profile(offer, profile)
    assert explanation.score is None
    assert explanation.positives == [] and explanation.negatives == []


def test_sparse_offer_fully_covered_scores_high():
    # OPP-151 (symptôme) : offre peu détaillée (contrat/séniorité/lieu « Non précisé »,
    # défaut LLM) dont tout ce qu'elle exige est couvert par un CV plus riche. Ces
    # dimensions non renseignées doivent être neutralisées (non évaluées), pas comptées
    # comme des 0 : le score reflète alors la seule dimension mesurable (skills) → 100.
    offer = _offer(
        skills=["Python"], contract_type="Non précisé",
        seniority="Non précisé", location="Non précisé",
    )
    profile = create_profile(name="Marie", skills=["Python", "React", "Docker"],
                             contract_type="CDI", location="Lyon", total_experience_years=6)
    result = score_offer_to_profile(offer, profile)
    assert result.score == 100
    assert result.breakdown["skills"].evaluated is True
    assert result.breakdown["contract_type"].evaluated is False
    assert result.breakdown["seniority"].evaluated is False
    assert result.breakdown["location"].evaluated is False
