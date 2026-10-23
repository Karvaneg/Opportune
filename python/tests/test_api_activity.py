"""Tests de l'endpoint de flux d'activité du cockpit (OPP-165).

``GET /candidates/{id}/activity`` : journal transversal horodaté, candidat inconnu → 404. Vrais
dépôts SQLite en mémoire ; lettres et actions câblées pour couvrir les quatre types d'événements.
Le gating identité/rôle est couvert par ``test_api_auth.py`` (local-first, OPP-181).
"""

import itertools

import pytest

from api.app import HermesApi
from app.action_service import ActionService
from app.action_store import ApplicationActionStore, OutboundMessageActionStore
from app.auth import REVIEWER, LocalAuthProvider, User
from app.candidate_profile import create_profile
from app.db import connect
from app.decision import decision_id
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.letter import Letter
from app.letter_service import LetterService
from app.letter_store import LetterStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _offer(**overrides) -> Offer:
    data = dict(
        id="o", title="T", company="Acme", location="Paris",
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
    letters_store = LetterStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python", "SQL"], contract_type="CDI",
        location="Paris", total_experience_years=6,
    ))
    offers.save(_offer(id="a", title="A", url="http://a", created_at="2026-01-01T00:00:00+00:00"))
    offers.save(_offer(id="b", title="B", url="http://b", created_at="2026-01-02T00:00:00+00:00"))
    offers.save(_offer(id="c", title="C", url="http://c", created_at="2026-01-03T00:00:00+00:00"))
    decisions = DecisionService(DecisionStore(conn), now=lambda: "2026-09-04T00:00:00+00:00")
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers), decisions,
        runs=RunStore(conn), run_id=lambda: "run-1", now=lambda: "2026-09-04T12:00:00+00:00",
    )
    ids = (str(n) for n in itertools.count(1))
    actions = ActionService(
        decisions, ApplicationActionStore(conn), OutboundMessageActionStore(conn),
        new_id=lambda: next(ids), now=lambda: "2026-09-05T00:00:00+00:00",
    )
    letters = LetterService(
        letters=letters_store, decisions=decisions, profiles=profiles, offers=offers, redacteur=None
    )
    # Identité locale : propriétaire reviewer de cand-1 (et cand-2, sans profil, pour le cas
    # « candidat inconnu »).
    auth = LocalAuthProvider(User("moi", REVIEWER, frozenset({"cand-1", "cand-2"})))
    api = HermesApi(orchestrator, actions, auth, letters=letters)
    return api, letters_store


def test_activity_lists_offer_additions_when_fresh(env):
    api, _ = env
    resp = api.dispatch("GET", "/candidates/cand-1/activity", None, None)
    assert resp.status == 200
    items = resp.body["items"]
    # Aucune décision/lettre/candidature encore → seulement les 3 offres ajoutées, récentes d'abord.
    assert [i["type"] for i in items] == ["offer", "offer", "offer"]
    assert items[0]["target_kind"] == "offer"
    assert "Offre ajoutée" in items[0]["label"]


def test_activity_aggregates_all_event_types_sorted(env):
    api, letters_store = env
    rid = decision_id("cand-1", "a")
    # Décision tranchée (approuvée) sur a, candidature déclarée sur a, lettre pour a.
    api.dispatch("POST", "/candidates/cand-1/offers/a/rescore", {}, None)
    api.dispatch("POST", f"/recommendations/{rid}/decision", {"decision": "approve"}, None)
    api.dispatch("POST", f"/applications/{rid}/confirm", {"confirm": True}, None)
    api.dispatch("POST", f"/applications/{rid}/applied", {}, None)
    letters_store.save(Letter(
        recommendation_id=rid, body="Madame…", source="ai", model="m",
        created_at="2026-09-06T00:00:00+00:00", updated_at="2026-09-06T00:00:00+00:00",
    ))

    items = api.dispatch("GET", "/candidates/cand-1/activity", None, None).body["items"]
    types = {i["type"] for i in items}
    assert {"decision", "application", "letter", "offer"} <= types
    # Horodatages décroissants.
    ats = [i["at"] for i in items]
    assert ats == sorted(ats, reverse=True)
    # La décision pointe vers la fiche de recommandation.
    decision_item = next(i for i in items if i["type"] == "decision")
    assert decision_item["target_kind"] == "recommendation" and decision_item["target_id"] == rid


def test_activity_unknown_candidate_is_404(env):
    api, _ = env
    # cand-2 est dans le périmètre mais n'a aucune donnée : candidat inconnu → 404.
    assert api.dispatch("GET", "/candidates/cand-2/activity", None, None).status == 404
