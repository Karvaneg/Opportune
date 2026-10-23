"""Tests des endpoints lettre de motivation (OPP-147).

On teste ``HermesApi.dispatch`` directement (aucun réseau) : rédacteur **stub**, dépôts
SQLite en mémoire. On couvre le contrat HTTP (verbes, codes, sérialisation), la règle
produit (409 si lettre existante, régénération explicite) et les gardes d'autorisation
(403/404 neutre), plus la route optionnelle (404 si service absent).
"""

import itertools

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User
from app.candidate_profile import create_profile
from app.cover_letter import CoverLetter, CoverLetterError
from app.db import connect
from app.decision import decision_id
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.letter_service import LetterService
from app.letter_store import LetterStore
from app.llm_client import LLMError
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore

_VALID_LETTER = (
    "Madame, Monsieur,\n\nVivement intéressée par votre offre, je vous adresse ma "
    "candidature ; mon profil backend correspond à vos attentes.\n\nCordialement,\nMarie"
)

RID = decision_id("cand-1", "off-app")


class StubRedacteur:
    def __init__(self, *, body=_VALID_LETTER, model="mock-model", raises=None):
        self._body, self._model, self._raises = body, model, raises
        self.calls = 0

    def write_cover_letter(self, offer, profile) -> CoverLetter:
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return CoverLetter.from_generation(self._body, model=self._model)


def _offer(**overrides) -> Offer:
    data = dict(
        id="off-app", title="Dev", company="Acme", location="Paris", skills=["Python"],
        seniority="Senior", contract_type="CDI", summary="s", attention_points=[],
        source="collée", url="", raw_text="brut",
    )
    data.update(overrides)
    return Offer(**data)


def _auth() -> LocalAuthProvider:
    # Identité locale par défaut des tests : propriétaire reviewer de cand-1.
    return LocalAuthProvider(User(id="moi", role=REVIEWER, owned_candidates=frozenset({"cand-1"})))


@pytest.fixture
def env():
    conn = connect(":memory:")
    profiles = ProfileStore(conn)
    offers = OfferStore(conn)
    decisions = DecisionStore(conn)
    letters_store = LetterStore(conn)
    profiles.save(create_profile(
        id="cand-1", name="Marie", skills=["Python"], contract_type="CDI",
    ))
    offers.save(_offer())
    clock = (f"t{n}" for n in itertools.count(0))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(decisions, now=lambda: next(clock)),
        runs=RunStore(conn),
        run_id=lambda: "run-1",
        now=lambda: "t-run",
    )
    redacteur = StubRedacteur()
    letters = LetterService(
        letters=letters_store, decisions=decisions, profiles=profiles,
        offers=offers, redacteur=redacteur, now=lambda: "t-gen",
    )
    api = HermesApi(orchestrator, auth=_auth(), letters=letters)
    # Crée la décision (reco) pending de off-app, sous l'identité propriétaire.
    api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    yield api, redacteur
    conn.close()


# --- Cycle nominal -----------------------------------------------------------

def test_post_generates_letter_201(env):
    api, redacteur = env
    resp = api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    assert resp.status == 201
    assert resp.body["source"] == "ai"
    assert resp.body["model"] == "mock-model"
    assert resp.body["recommendation_id"] == RID
    assert set(resp.body) == {
        "recommendation_id", "body", "source", "model", "created_at", "updated_at",
    }
    assert redacteur.calls == 1


def test_get_returns_letter(env):
    api, _ = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    resp = api.dispatch("GET", f"/recommendations/{RID}/letter", None)
    assert resp.status == 200
    assert resp.body["body"].startswith("Madame")


def test_get_absent_letter_404(env):
    api, _ = env
    assert api.dispatch("GET", f"/recommendations/{RID}/letter", None).status == 404


def test_post_twice_conflict_409(env):
    api, redacteur = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    resp = api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    assert resp.status == 409
    assert redacteur.calls == 1  # pas de régénération silencieuse


def test_post_regenerate_true_overwrites_200(env):
    api, redacteur = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    resp = api.dispatch("POST", f"/recommendations/{RID}/letter", {"regenerate": True})
    assert resp.status == 200
    assert redacteur.calls == 2
    assert resp.body["source"] == "ai"


def test_put_edits_letter_human_source(env):
    api, _ = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    body = "Version entièrement réécrite à la main par la candidate, bien assez longue."
    resp = api.dispatch("PUT", f"/recommendations/{RID}/letter", {"body": body})
    assert resp.status == 200
    assert resp.body["source"] == "human"
    assert resp.body["body"] == body
    assert resp.body["model"] == ""


def test_post_after_human_edit_still_conflicts(env):
    api, _ = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    api.dispatch("PUT", f"/recommendations/{RID}/letter", {"body": "Édition humaine conservée ici."})
    # Re-POST sans regenerate : protège l'édition (409), ne régénère pas.
    assert api.dispatch("POST", f"/recommendations/{RID}/letter", {}).status == 409
    # L'édition humaine est intacte.
    got = api.dispatch("GET", f"/recommendations/{RID}/letter", None)
    assert got.body["source"] == "human"


def test_delete_then_absent(env):
    api, _ = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    assert api.dispatch("DELETE", f"/recommendations/{RID}/letter", None).status == 200
    assert api.dispatch("GET", f"/recommendations/{RID}/letter", None).status == 404
    # Idempotence douce : re-supprimer → 404 neutre.
    assert api.dispatch("DELETE", f"/recommendations/{RID}/letter", None).status == 404


# --- Validation du corps -----------------------------------------------------

@pytest.mark.parametrize("body", [{}, {"body": "   "}, {"body": 123}])
def test_put_rejects_empty_or_non_string_body(env, body):
    api, _ = env
    api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    assert api.dispatch("PUT", f"/recommendations/{RID}/letter", body).status == 400


def test_put_without_existing_letter_404(env):
    api, _ = env
    resp = api.dispatch("PUT", f"/recommendations/{RID}/letter", {"body": "un corps valide et assez long"})
    assert resp.status == 404


def test_post_rejects_non_boolean_regenerate(env):
    api, _ = env
    resp = api.dispatch("POST", f"/recommendations/{RID}/letter", {"regenerate": "yes"})
    assert resp.status == 400


# --- Erreurs LLM → 502 -------------------------------------------------------

def test_post_maps_llm_error_to_502(env):
    api, redacteur = env
    api.letters.redacteur = StubRedacteur(raises=LLMError("ollama indisponible"))
    resp = api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    assert resp.status == 502


def test_post_maps_cover_letter_error_to_502(env):
    api, _ = env
    api.letters.redacteur = StubRedacteur(raises=CoverLetterError("génération vide"))
    resp = api.dispatch("POST", f"/recommendations/{RID}/letter", {})
    assert resp.status == 502


# --- Gardes d'authentification ----------------------------------------------

def test_non_reviewer_forbidden_403(env):
    api, _ = env
    # Même données, identité propriétaire mais non reviewer → 403.
    viewer = HermesApi(
        api.orchestrator,
        auth=LocalAuthProvider(User("moi", "viewer", frozenset({"cand-1"}))),
        letters=api.letters,
    )
    assert viewer.dispatch("POST", f"/recommendations/{RID}/letter", {}).status == 403


def test_other_owner_gets_neutral_404(env):
    api, _ = env
    # Reviewer d'un autre périmètre : 404 neutre (ne révèle pas l'existence de la reco).
    foreign = HermesApi(
        api.orchestrator,
        auth=LocalAuthProvider(User("autre", REVIEWER, frozenset({"cand-2"}))),
        letters=api.letters,
    )
    assert foreign.dispatch("POST", f"/recommendations/{RID}/letter", {}).status == 404


def test_unknown_recommendation_404(env):
    api, _ = env
    assert api.dispatch("GET", "/recommendations/cand-1:inexistante/letter", None).status == 404


# --- Route optionnelle -------------------------------------------------------

def test_letter_route_not_mounted_when_service_absent():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator, auth=_auth())  # pas de letters
    resp = api.dispatch("GET", f"/recommendations/{RID}/letter", None)
    assert resp.status == 404
    conn.close()
