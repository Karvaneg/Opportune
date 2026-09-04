"""Tests de la traçabilité et de l'idempotence Hermes (OPP-092).

Vrais dépôts SQLite en mémoire : aucun réseau, aucune I/O disque. On vérifie
l'enregistrement d'une exécution, la reprise après erreur (erreurs par offre tracées,
exécution suivante qui complète) et l'absence de doublons de décisions.
"""

import itertools

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.decision import decision_id
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService, UnknownCandidateError

from hermes.models import HermesRun
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _offer(**overrides) -> Offer:
    data = dict(
        id="o", title="Offre", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


class _FlakyDecisions:
    """Enveloppe un DecisionService réel mais échoue sur certaines offres (simulation)."""

    def __init__(self, real: DecisionService, failing_offer_ids: set[str]) -> None:
        self._real = real
        self._failing = set(failing_offer_ids)

    def decide(self, recommendation, candidate_id):
        if recommendation.offer.id in self._failing:
            raise RuntimeError("échec simulé")
        return self._real.decide(recommendation, candidate_id)

    def __getattr__(self, name):
        # Tout le reste (evaluate, get, validate, list_for_candidate…) est délégué au
        # service réel : le fake ne surcharge que ``decide`` pour simuler des échecs.
        return getattr(self._real, name)


@pytest.fixture
def env():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decisions = DecisionStore(conn)
    runs = RunStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    decision_service = DecisionService(decisions, now=lambda: "2026-09-03T00:00:00+00:00")
    run_ids = (f"run-{n}" for n in itertools.count(1))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        decision_service,
        runs=runs,
        run_id=lambda: next(run_ids),
        now=lambda: "2026-09-03T12:00:00+00:00",
    )
    yield orchestrator, offers, decisions, runs
    conn.close()


def _seed_two(offers):
    offers.save(_offer(id="a", title="A", url="http://a"))  # → 100
    offers.save(_offer(id="b", title="B", url="http://b", skills=["Python", "Go"]))  # → 78


def test_run_records_execution(env):
    orchestrator, offers, decisions, runs = env
    _seed_two(offers)

    run = orchestrator.run_for_candidate("cand-1")

    assert run.run_id == "run-1"
    assert run.candidate_id == "cand-1"
    assert run.executed_at == "2026-09-03T12:00:00+00:00"
    assert [(e.offer_id, e.score, e.decision_status) for e in run.evaluations] == [
        ("a", 100, "pending"),
        ("b", 78, "pending"),
    ]
    assert run.errors == ()
    # Exécution persistée à l'identique, et décisions persistées.
    assert runs.get("run-1") == run
    assert isinstance(runs.get("run-1"), HermesRun)
    assert decisions.count() == 2


def test_run_records_errors_and_continues(env):
    orchestrator, offers, decisions, runs = env
    _seed_two(offers)
    # La décision échoue sur l'offre "a" : elle est tracée, "b" est tout de même évaluée.
    orchestrator.decisions = _FlakyDecisions(orchestrator.decisions, {"a"})

    run = orchestrator.run_for_candidate("cand-1")

    assert [e.offer_id for e in run.evaluations] == ["b"]
    assert len(run.errors) == 1 and run.errors[0].startswith("a: ")
    assert decisions.get(decision_id("cand-1", "a")) is None  # rien de persisté pour "a"
    assert decisions.count() == 1
    assert runs.get("run-1").errors == run.errors  # erreurs journalisées


def test_rerun_after_error_resumes(env):
    orchestrator, offers, decisions, runs = env
    _seed_two(offers)
    healthy = orchestrator.decisions
    orchestrator.decisions = _FlakyDecisions(healthy, {"a"})

    first = orchestrator.run_for_candidate("cand-1")  # "a" échoue
    assert first.errors and decisions.get(decision_id("cand-1", "a")) is None

    # Reprise : service sain → l'exécution suivante complète ce qui manquait.
    orchestrator.decisions = healthy
    second = orchestrator.run_for_candidate("cand-1")

    assert second.run_id == "run-2"
    assert second.errors == ()
    assert [e.offer_id for e in second.evaluations] == ["a", "b"]
    assert decisions.get(decision_id("cand-1", "a")) is not None
    assert decisions.count() == 2


def test_reruns_do_not_duplicate_decisions(env):
    orchestrator, offers, decisions, runs = env
    _seed_two(offers)

    orchestrator.run_for_candidate("cand-1")
    orchestrator.run_for_candidate("cand-1")  # même candidat, mêmes offres

    # Idempotence : upsert sur (candidat, offre) → pas de doublon de décision.
    assert decisions.count() == 2
    # Chaque exécution reste tracée distinctement (run_id unique).
    assert runs.count() == 2
    assert runs.get("run-1").run_id == "run-1"
    assert runs.get("run-2").run_id == "run-2"


def test_unknown_candidate_raises_and_records_no_run(env):
    orchestrator, _, _, runs = env
    with pytest.raises(UnknownCandidateError):
        orchestrator.run_for_candidate("nope")
    assert runs.count() == 0
