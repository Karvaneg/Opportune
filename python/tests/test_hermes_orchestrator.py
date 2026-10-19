"""Tests de l'orchestrateur Hermes (OPP-060).

Vrais dépôts SQLite en mémoire : aucun réseau, aucune I/O disque. Hermes coordonne
``RecommendationService`` et ``DecisionStore`` ; on vérifie le câblage (ordre, décisions
persistées, propagation d'erreurs), pas la logique déléguée (déjà couverte ailleurs).
"""

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.decision import DecisionError, PENDING, decision_id
from app.decision_service import DecisionService, UnknownDecisionError
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService, UnknownCandidateError

from hermes.models import HermesRecommendation
from hermes.orchestrator import HermesOrchestrator


def _offer(**overrides) -> Offer:
    data = dict(
        id="o", title="Offre", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


@pytest.fixture
def env():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decisions = DecisionStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    service = RecommendationService(profiles, offers)
    decision_service = DecisionService(decisions, now=lambda: "2026-09-03T00:00:00+00:00")
    orchestrator = HermesOrchestrator(service, decision_service)
    yield orchestrator, offers, decisions
    conn.close()


# Dates croissantes a < b < c → ordre par date décroissante c, b, a (inverse du score).
def _seed_three(offers):
    offers.save(_offer(id="a", title="A", url="http://a",
                       created_at="2026-01-01T00:00:00+00:00"))  # parfaite → 100, plus ancienne
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"],
                       created_at="2026-01-02T00:00:00+00:00"))  # → 78
    offers.save(_offer(  # faible → 11 (séniorité 6/8 graduée), plus récente
        id="c", title="C", url="http://c", skills=["Java"],
        contract_type="Freelance", location="Lyon", seniority="Lead",
        created_at="2026-01-03T00:00:00+00:00",
    ))


def test_returns_recommendations_ordered_by_date(env):
    # OPP-152 : plus récentes d'abord (c, b, a), score toujours attaché.
    orchestrator, offers, _ = env
    _seed_three(offers)
    results = orchestrator.recommend_for_candidate("cand-1")
    assert all(isinstance(r, HermesRecommendation) for r in results)
    assert [(r.recommendation.offer.id, r.recommendation.score) for r in results] == [
        ("c", 0), ("b", 78), ("a", 100),
    ]


def test_creates_and_persists_a_pending_decision_per_recommendation(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    results = orchestrator.recommend_for_candidate("cand-1")
    assert decisions.count() == 3
    for r in results:
        stored = decisions.get(decision_id("cand-1", r.recommendation.offer.id))
        assert stored is not None
        assert stored == r.decision
        assert stored.status == PENDING
        # La décision reprend fidèlement la recommandation (rien de réimplémenté).
        assert stored.action == r.recommendation.action
        assert stored.score == r.recommendation.score
        assert stored.justification == r.recommendation.justification


def test_respects_limit(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    results = orchestrator.recommend_for_candidate("cand-1", limit=1)
    assert [r.recommendation.offer.id for r in results] == ["c"]  # la plus récente
    assert decisions.count() == 1  # seules les décisions retenues sont persistées


def test_unknown_candidate_raises_and_persists_nothing(env):
    orchestrator, _, decisions = env
    with pytest.raises(UnknownCandidateError):
        orchestrator.recommend_for_candidate("nope")
    assert decisions.count() == 0


def test_negative_limit_rejected_and_persists_nothing(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    with pytest.raises(ValueError):
        orchestrator.recommend_for_candidate("cand-1", limit=-1)
    assert decisions.count() == 0


def test_validate_decision_applies_human_status(env):
    orchestrator, offers, decisions = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    orchestrator.recommend_for_candidate("cand-1")  # crée la décision pending
    updated = orchestrator.validate_decision("cand-1", "a", "approved", comment="go")
    assert updated.status == "approved"
    assert updated.comment == "go"
    assert decisions.get(decision_id("cand-1", "a")).status == "approved"


def test_validate_decision_unknown_raises(env):
    orchestrator, _, _ = env
    with pytest.raises(UnknownDecisionError):
        orchestrator.validate_decision("cand-1", "a", "approved")


def test_validate_decision_invalid_status_raises(env):
    orchestrator, offers, _ = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    orchestrator.recommend_for_candidate("cand-1")
    with pytest.raises(DecisionError):
        orchestrator.validate_decision("cand-1", "a", "pending")


def test_empty_stock_returns_empty(env):
    orchestrator, _, decisions = env
    assert orchestrator.recommend_for_candidate("cand-1") == []
    assert decisions.count() == 0


def test_integration_two_offers_sort_and_limit(env):
    """Intégration bout-en-bout : 1 candidat, 2 offres, l'une meilleure mais plus ancienne.

    Couvre en un scénario le tri **par date** (plus récente en tête, OPP-152) et ``limit`` —
    en prouvant que l'ordre ne suit PAS le score (la faible, plus récente, passe devant).
    """
    orchestrator, offers, _ = env
    # Offre forte : profil parfait → score élevé, mais ingérée en premier (plus ancienne).
    offers.save(_offer(id="offer-forte", title="Forte", url="http://forte",
                       created_at="2026-01-01T00:00:00+00:00"))
    # Offre faible : une seule compétence en commun → score inférieur, mais plus récente.
    offers.save(_offer(id="offer-faible", title="Faible", url="http://faible",
                       skills=["Python", "Go"], created_at="2026-02-01T00:00:00+00:00"))

    results = orchestrator.recommend_for_candidate("cand-1")

    # Résultat uniforme.
    assert all(isinstance(r, HermesRecommendation) for r in results)
    # Tri par date : la plus récente (faible) est en tête, malgré un score plus bas.
    assert [r.recommendation.offer.id for r in results] == ["offer-faible", "offer-forte"]
    assert results[0].recommendation.score < results[1].recommendation.score

    # Limite : ne retourne que la plus récente.
    top = orchestrator.recommend_for_candidate("cand-1", limit=1)
    assert [r.recommendation.offer.id for r in top] == ["offer-faible"]


def test_rerun_upserts_decisions_without_duplicating(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    orchestrator.recommend_for_candidate("cand-1")
    orchestrator.recommend_for_candidate("cand-1")  # même candidat, mêmes offres
    assert decisions.count() == 3  # upsert sur le couple candidat/offre, pas de doublon


def test_rerun_preserves_human_validation(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    orchestrator.recommend_for_candidate("cand-1")
    orchestrator.validate_decision("cand-1", "a", "approved", comment="go")
    # Re-dérouler Hermes ne doit pas réinitialiser la décision validée à pending.
    results = orchestrator.recommend_for_candidate("cand-1")
    top = next(r for r in results if r.recommendation.offer.id == "a")
    assert top.decision.status == "approved"
    assert top.decision.comment == "go"
    stored = decisions.get(decision_id("cand-1", "a"))
    assert stored.status == "approved"
    assert len(stored.history) == 2  # pending + approved, non écrasé
    assert decisions.count() == 3


def test_injected_clock_stamps_decision_history(env):
    orchestrator, offers, decisions = env
    offers.save(_offer(id="a", title="A", url="http://a"))
    result = orchestrator.recommend_for_candidate("cand-1")[0]
    assert result.decision.history[0].at == "2026-09-03T00:00:00+00:00"


def _seed_one_per_bucket(offers):
    """Sème 3 offres calibrées pour tomber dans chacun des 3 statuts de triage.

    Profil : Python+SQL, CDI, Paris, 6 ans. Seuils 80 / 60. Poids skills .45 /
    contrat .30 / séniorité .15 / lieu .10.
    """
    # Dates décroissantes app > pend > rej : la plus récente (off-app) est en tête de liste.
    # Parfaite → 100 → postuler → approved.
    offers.save(_offer(id="off-app", title="App", url="http://app",
                       created_at="2026-03-01T00:00:00+00:00"))
    # 1/2 compétence + lieu différent → 68 → a_etudier → pending.
    #   skills .5*.45=.225 + contrat 1*.30 + séniorité 1*.15 + lieu 0*.10 = .675 → 68.
    offers.save(_offer(id="off-pend", title="Pend", url="http://pend",
                       skills=["Python", "Java"], location="Lyon",
                       created_at="2026-02-01T00:00:00+00:00"))
    # Tout discordant → 0 → ignorer → rejected.
    offers.save(_offer(id="off-rej", title="Rej", url="http://rej",
                       skills=["Cobol"], contract_type="Freelance",
                       location="Lyon", seniority="Lead",
                       created_at="2026-01-01T00:00:00+00:00"))


def test_evaluate_for_candidate_buckets_approved_pending_rejected(env):
    orchestrator, offers, decisions = env
    _seed_one_per_bucket(offers)

    result = orchestrator.evaluate_for_candidate("cand-1")

    assert result["candidate_id"] == "cand-1"
    assert [r.offer.id for r in result["recommendations"]] == ["off-app"]
    assert [r.offer.id for r in result["pending_review"]] == ["off-pend"]
    assert [r.offer.id for r in result["rejected"]] == ["off-rej"]
    # Triage pur : aucune décision persistée par ce chemin.
    assert decisions.count() == 0


def test_evaluate_for_candidate_respects_limit(env):
    orchestrator, offers, _ = env
    _seed_one_per_bucket(offers)
    # limit=1 ne garde que la plus récente (off-app, ici aussi la meilleure) ; autres buckets vides.
    result = orchestrator.evaluate_for_candidate("cand-1", limit=1)
    assert [r.offer.id for r in result["recommendations"]] == ["off-app"]
    assert result["pending_review"] == []
    assert result["rejected"] == []


def test_evaluate_for_candidate_unknown_candidate_raises(env):
    orchestrator, _, _ = env
    with pytest.raises(UnknownCandidateError):
        orchestrator.evaluate_for_candidate("nope")


# --- OPP-150 : un run n'évalue que les offres nouvelles + re-score ciblé --------


def test_run_excludes_already_decided_offers(env):
    orchestrator, offers, _ = env
    _seed_three(offers)
    # 1er run : toutes les offres sont nouvelles → évaluées (décisions pending créées).
    first = orchestrator.run_and_evaluate_for_candidate("cand-1", only_new=True)
    assert {e.offer_id for e in first.evaluations} == {"a", "b", "c"}
    # Une nouvelle offre arrive ; le 2e run n'évalue qu'elle (les 3 autres sont « anciennes »).
    offers.save(_offer(id="d", title="D", url="http://d"))
    second = orchestrator.run_and_evaluate_for_candidate("cand-1", only_new=True)
    assert [e.offer_id for e in second.evaluations] == ["d"]


def test_run_without_new_offers_is_empty(env):
    orchestrator, offers, _ = env
    _seed_three(offers)
    orchestrator.run_and_evaluate_for_candidate("cand-1", only_new=True)  # consomme tout
    again = orchestrator.run_and_evaluate_for_candidate("cand-1", only_new=True)
    assert again.evaluations == ()


def test_run_without_only_new_reevaluates_whole_pool(env):
    # Régression : sans only_new (ex. push Discord), le run re-déroule tout le pool.
    orchestrator, offers, _ = env
    _seed_three(offers)
    orchestrator.run_and_evaluate_for_candidate("cand-1")
    again = orchestrator.run_and_evaluate_for_candidate("cand-1")
    assert {e.offer_id for e in again.evaluations} == {"a", "b", "c"}


def test_rescore_offer_creates_pending_decision(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    decision = orchestrator.rescore_offer("cand-1", "b")
    assert decision is not None
    assert decision.offer_id == "b"
    assert decision.score == 78
    assert decision.status == PENDING
    assert decisions.get(decision_id("cand-1", "b")).score == 78


def test_rescore_offer_creates_decidable_fiche_for_formation(env):
    # OPP-166 : ouvrir une formation crée bien une décision (fiche décidable : validation,
    # candidature, lettre), mais sans score d'adéquation — se former peut être une candidature.
    orchestrator, offers, decisions = env
    offers.save(_offer(id="f", title="Bootcamp Data", url="http://f", kind="formation"))
    decision = orchestrator.rescore_offer("cand-1", "f")
    assert decision is not None
    assert decision.offer_id == "f"
    assert decision.score is None
    assert decision.action == "indeterminee"
    assert decision.status == PENDING
    assert decisions.get(decision_id("cand-1", "f")).score is None


def test_rescore_offer_preserves_human_decision(env):
    orchestrator, offers, decisions = env
    _seed_three(offers)
    orchestrator.rescore_offer("cand-1", "a")  # crée la décision pending
    orchestrator.validate_decision("cand-1", "a", "approved", comment="go")
    # Re-scorer une offre déjà arbitrée ne doit jamais écraser la décision humaine.
    result = orchestrator.rescore_offer("cand-1", "a")
    assert result.status == "approved"
    assert result.comment == "go"
    assert decisions.get(decision_id("cand-1", "a")).status == "approved"


def test_rescore_offer_none_when_offer_absent(env):
    orchestrator, offers, _ = env
    _seed_three(offers)
    assert orchestrator.rescore_offer("cand-1", "nope") is None


def test_candidate_stats_counts_actionable_and_pool(env):
    # OPP-163 : a→postuler (100), b→a_etudier (78), c→ignorer. Aucune décision tranchée.
    orchestrator, offers, _ = env
    _seed_three(offers)
    stats = orchestrator.candidate_stats("cand-1", applied_count=2)
    assert stats.a_postuler == 1   # a
    assert stats.a_etudier == 1    # b
    assert stats.postule == 2      # replié depuis l'appelant
    assert stats.offres_total == 3


def test_candidate_stats_excludes_tranchees_from_piles(env):
    # Une décision humaine déjà prise sort l'offre des piles « à traiter ».
    orchestrator, offers, _ = env
    _seed_three(offers)
    orchestrator.rescore_offer("cand-1", "a")  # crée la décision pending de a (postuler)
    orchestrator.validate_decision("cand-1", "a", "approved", comment="go")
    stats = orchestrator.candidate_stats("cand-1")
    assert stats.a_postuler == 0   # a est tranchée → plus « à postuler »
    assert stats.a_etudier == 1    # b reste pending
    assert stats.offres_total == 3


def test_candidate_stats_formation_counts_in_pool_only(env):
    # OPP-166 × OPP-163 : une formation gonfle offres_total mais pas les piles d'action.
    orchestrator, offers, _ = env
    _seed_three(offers)
    offers.save(_offer(id="f", title="Formation", url="http://f", kind="formation"))
    stats = orchestrator.candidate_stats("cand-1")
    assert stats.offres_total == 4
    assert stats.a_postuler == 1 and stats.a_etudier == 1  # inchangé par la formation


def test_candidate_stats_unknown_candidate_raises(env):
    orchestrator, _, _ = env
    with pytest.raises(UnknownCandidateError):
        orchestrator.candidate_stats("nope")


def test_rescore_offer_unknown_candidate_raises(env):
    orchestrator, offers, _ = env
    _seed_three(offers)
    with pytest.raises(UnknownCandidateError):
        orchestrator.rescore_offer("nope", "a")
