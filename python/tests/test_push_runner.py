"""Tests du runner de la boucle push (OPP-128).

Adaptateur mince : on vérifie le **câblage** (enchaînement intake → run → résolution →
lettre → push, lecture d'env, timeout généreux, échecs partiels), pas la logique déléguée
— déjà couverte en aval. Vrais dépôts SQLite en mémoire, LLM et Discord mockés : zéro réseau.
"""

import json

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.discord_review import DiscordReviewer
from app.discord_transport import DiscordError, MockDiscordTransport
from app.llm_client import MockLLMClient
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService, UnknownCandidateError
from app.redacteur import LLMRedacteur
from app.review_pipeline import BatchReviewError

from hermes.orchestrator import HermesOrchestrator
from hermes.push_runner import (
    DEFAULT_LLM_TIMEOUT,
    PushOutcome,
    PushRunner,
    build_push_runner,
    resolve_llm_timeout,
)
from hermes.run_store import RunStore

LETTER = ("Madame, Monsieur, " + "texte de motivation " * 15).strip()


def _analysis(**overrides) -> str:
    data = {
        "title": "Développeur Python Senior", "company": "Acme", "location": "Paris",
        "seniority": "Senior", "contract_type": "CDI", "summary": "Backend data.",
        "skills": ["Python", "SQL"], "attention_points": [],
    }
    data.update(overrides)
    return json.dumps(data)


def _offer(offer_id: str, **overrides) -> Offer:
    data = dict(
        id=offer_id, title="Offre", company="Acme", location="Paris",
        skills=["Python", "SQL"], seniority="Senior", contract_type="CDI",
        summary="s", attention_points=[], source="indeed", url="http://x", raw_text="t",
    )
    data.update(overrides)
    return Offer(**data)


def _build(conn, *, intake=None, redacteur=None, transport=None, limit=10, with_profile=True):
    """Assemble un PushRunner sur de vrais dépôts, LLM/Discord mockés."""
    offers = OfferStore(conn)
    profiles = ProfileStore(conn)
    decisions = DecisionStore(conn)
    if with_profile:
        profiles.save(create_profile(
            id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
            location="Paris", total_experience_years=6,
        ))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(decisions, now=lambda: "2026-09-09T00:00:00+00:00"),
        runs=RunStore(conn),
    )
    transport = transport or MockDiscordTransport()
    runner = PushRunner(
        orchestrator=orchestrator, decisions=decisions, offers=offers, profiles=profiles,
        redacteur=redacteur or LLMRedacteur(MockLLMClient([LETTER] * 5)),
        reviewer=DiscordReviewer(transport, channel_id="chan-1"),
        intake_client=intake or MockLLMClient([_analysis()] * 5),
        limit=limit,
    )
    return runner, transport


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


# --- push sur stock existant --------------------------------------------------


def test_push_for_candidate_pushes_only_eligible_cards(conn):
    runner, transport = _build(conn)
    runner.offers.save(_offer("strong"))  # parfaite → 100 → postuler → poussée
    runner.offers.save(_offer(  # faible → 0 → ignorer → non éligible
        "weak", skills=["Java"], contract_type="Freelance", location="Lyon", seniority="Lead",
    ))

    outcome = runner.push_for_candidate("cand-1")

    assert isinstance(outcome, PushOutcome)
    assert [r.recommendation_id for r in outcome.reviewed] == ["cand-1:strong"]
    assert len(transport.sent) == 1
    assert outcome.missing_offers == ()
    # Les décisions ont bien été persistées par le run (les deux offres évaluées).
    assert runner.decisions.count() == 2


def test_push_carries_the_generated_letter_to_discord(conn):
    runner, transport = _build(conn)
    runner.offers.save(_offer("strong"))

    runner.push_for_candidate("cand-1")

    sent = transport.sent[0]["message"]
    assert sent["embeds"][0]["description"] == LETTER


# --- ingestion puis push ------------------------------------------------------


def test_run_ingests_then_pushes(conn):
    # Aucune offre en stock : l'offre collée est analysée, persistée, puis poussée.
    runner, transport = _build(conn, intake=MockLLMClient([_analysis()]))

    outcome = runner.run(["texte d'offre collé"], "cand-1", source="collée")

    assert runner.offers.count() == 1
    assert len(outcome.reviewed) == 1
    assert len(transport.sent) == 1


def test_run_unknown_candidate_raises_before_any_ingest(conn):
    intake = MockLLMClient([_analysis()])
    runner, _ = _build(conn, intake=intake, with_profile=False)

    with pytest.raises(UnknownCandidateError):
        runner.run(["texte"], "cand-1", source="collée")

    # Échec net : rien n'a été analysé ni persisté à vide.
    assert intake.calls == []
    assert runner.offers.count() == 0


# --- échec partiel ------------------------------------------------------------


class _FailOnNthTransport:
    """Transport Discord qui pousse puis échoue au ``fail_on``-ième envoi."""

    def __init__(self, *, fail_on: int) -> None:
        self.fail_on = fail_on
        self.sent: list[dict] = []

    def send_message(self, channel_id: str, message: dict) -> dict:
        self.sent.append({"channel_id": channel_id, "message": message})
        if len(self.sent) == self.fail_on:
            raise DiscordError("boom")
        return {"id": f"msg-{len(self.sent)}", "channel_id": channel_id}


def test_partial_failure_propagates_batch_review_error(conn):
    transport = _FailOnNthTransport(fail_on=2)
    runner, _ = _build(conn, transport=transport)
    runner.offers.save(_offer("a"))
    runner.offers.save(_offer("b"))  # deux offres parfaites → deux postuler éligibles

    with pytest.raises(BatchReviewError) as err:
        runner.push_for_candidate("cand-1")

    # Progression préservée : la 1re carte est poussée, l'échec porte sur la 2de.
    assert len(err.value.results) == 1
    assert len(transport.sent) == 2


# --- câblage d'environnement --------------------------------------------------


def test_resolve_llm_timeout_defaults_when_absent():
    assert resolve_llm_timeout({}) == DEFAULT_LLM_TIMEOUT
    assert resolve_llm_timeout({"OPPORTUNE_LLM_TIMEOUT": ""}) == DEFAULT_LLM_TIMEOUT


def test_resolve_llm_timeout_reads_env():
    assert resolve_llm_timeout({"OPPORTUNE_LLM_TIMEOUT": "240"}) == 240


@pytest.mark.parametrize("bad", ["abc", "0", "-5"])
def test_resolve_llm_timeout_rejects_invalid(bad):
    with pytest.raises(ValueError):
        resolve_llm_timeout({"OPPORTUNE_LLM_TIMEOUT": bad})


def test_build_push_runner_wires_generous_timeout(conn):
    runner = build_push_runner(
        conn,
        env={
            "DISCORD_CHANNEL_ID": "chan-1",
            "DISCORD_BOT_TOKEN": "tok",
            "OPPORTUNE_LLM_TIMEOUT": "240",
        },
    )
    assert runner.intake_client.timeout == 240
    # À défaut de variable, le défaut généreux est câblé (jamais le 60 s d'app.llm).
    runner_default = build_push_runner(
        conn, env={"DISCORD_CHANNEL_ID": "chan-1", "DISCORD_BOT_TOKEN": "tok"}
    )
    assert runner_default.intake_client.timeout == DEFAULT_LLM_TIMEOUT


def test_build_push_runner_requires_channel(conn):
    with pytest.raises(ValueError):
        build_push_runner(conn, env={"DISCORD_BOT_TOKEN": "tok"})


def test_build_push_runner_requires_token(conn):
    # Le token est validé au démarrage, pas seulement au premier envoi Discord :
    # sinon l'intake LLM et le run Hermes s'exécuteraient avant de crasher.
    with pytest.raises(ValueError):
        build_push_runner(conn, env={"DISCORD_CHANNEL_ID": "chan-1"})
