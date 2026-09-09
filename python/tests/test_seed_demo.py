"""Tests du seed de démo (OPP-132).

SQLite en mémoire, aucun réseau. On vérifie que le seed pose des données cohérentes,
qu'il est idempotent, et qu'il suffit à produire une carte via le runner push (mocké).
"""

import pytest

from app.candidate_profile import create_profile
from app.db import connect
from app.discord_review import DiscordReviewer
from app.discord_transport import MockDiscordTransport
from app.llm_client import MockLLMClient
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from app.redacteur import LLMRedacteur
from app.decision_service import DecisionService
from app.decision_store import DecisionStore

from hermes.orchestrator import HermesOrchestrator
from hermes.push_runner import PushRunner
from hermes.run_store import RunStore
from hermes.seed_demo import DEMO_OFFER_ID, seed_demo

LETTER = ("Madame, Monsieur, " + "texte de motivation " * 15).strip()


@pytest.fixture
def stores():
    conn = connect(":memory:")
    yield ProfileStore(conn), OfferStore(conn), conn
    conn.close()


def test_seed_persists_aligned_profile_and_offer(stores):
    profiles, offers, _ = stores

    profile, offer = seed_demo(profiles, offers, candidate_id="cand-1")

    assert profiles.get("cand-1") == profile
    assert offers.get(DEMO_OFFER_ID) == offer
    # Profil et offre alignés (mêmes skills/contrat/lieu) → matchables.
    assert set(profile.skills) == set(offer.skills)
    assert profile.contract_type == offer.contract_type


def test_seed_preserves_existing_profile(stores):
    profiles, offers, _ = stores
    # Un vrai profil, sous le même id que ciblera le seed (l'identité de prod).
    existing = create_profile(
        id="cand-1",
        name="Marie Réelle",
        skills=["Rust", "Go", "Kubernetes"],
        contract_type="freelance",
        total_experience_years=12,
    )
    profiles.save(existing)

    profile, _ = seed_demo(profiles, offers, candidate_id="cand-1")

    # Le seed comble une absence de profil ; il ne remplace jamais des données réelles.
    assert profile == existing
    assert profiles.get("cand-1") == existing


def test_seed_is_idempotent(stores):
    profiles, offers, _ = stores

    seed_demo(profiles, offers, candidate_id="cand-1")
    seed_demo(profiles, offers, candidate_id="cand-1")  # rejoué : pas de doublon

    assert offers.count() == 1


def test_seeded_data_produces_a_pushed_card(stores):
    profiles, offers, conn = stores
    seed_demo(profiles, offers, candidate_id="cand-1")

    decisions = DecisionStore(conn)
    transport = MockDiscordTransport()
    runner = PushRunner(
        orchestrator=HermesOrchestrator(
            RecommendationService(profiles, offers),
            DecisionService(decisions),
            runs=RunStore(conn),
        ),
        decisions=decisions,
        offers=offers,
        profiles=profiles,
        redacteur=LLMRedacteur(MockLLMClient([LETTER])),
        reviewer=DiscordReviewer(transport, channel_id="chan-1"),
        intake_client=MockLLMClient([]),
    )

    outcome = runner.push_for_candidate("cand-1")

    # Le seed suffit : une carte « postuler » est poussée sans saisie manuelle.
    assert [r.recommendation_id for r in outcome.reviewed] == [f"cand-1:{DEMO_OFFER_ID}"]
    assert len(transport.sent) == 1
