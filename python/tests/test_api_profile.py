"""Tests des routes de profil candidat (GET/PUT /candidates/{id}/profile, OPP-158).

Service profil réel adossé à un dépôt factice : on vérifie le contrat HTTP — sérialisation,
garde propriétaire (404 neutre hors périmètre), garde reviewer sur l'édition, validation du
corps, 404 profil absent, route optionnelle, et méthode non supportée.
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, AuthProvider, User
from app.candidate_profile import create_profile
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_store import OfferStore
from app.profile_service import ProfileService
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


class FakeProfileStore:
    def __init__(self, *profiles):
        self.saved = {p.id: p for p in profiles}

    def get(self, profile_id):
        return self.saved.get(profile_id)

    def save(self, profile):
        self.saved[profile.id] = profile


def _profile(candidate_id="cand-1", skills=("React",)):
    return create_profile(
        id=candidate_id, name="Marie", skills=list(skills), contract_type="CDI"
    )


def _api(profiles, *, auth=None) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=auth, profiles=profiles)


def _service(*profiles):
    return ProfileService(FakeProfileStore(*profiles))


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _auth():
    return AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-view": User("view", "viewer", frozenset({"cand-1"})),
        "tok-other": User("other", REVIEWER, frozenset({"cand-2"})),
    })


# --- GET ---------------------------------------------------------------------

def test_get_profile_serializes_fields():
    api = _api(_service(_profile(skills=["React", "HTML5"])))
    resp = api.dispatch("GET", "/candidates/cand-1/profile", None, None)
    assert resp.status == 200
    assert resp.body["id"] == "cand-1"
    assert resp.body["name"] == "Marie"
    assert resp.body["skills"] == ["React", "HTML5"]
    assert resp.body["contract_type"] == "CDI"


def test_get_profile_404_when_candidate_has_no_profile():
    api = _api(_service())  # aucun profil enregistré
    assert api.dispatch("GET", "/candidates/cand-1/profile", None, None).status == 404


def test_get_profile_route_absent_without_service():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator)  # pas de service profil → route non montée
    assert api.dispatch("GET", "/candidates/cand-1/profile", None, None).status == 404


def test_get_profile_owner_gated():
    api = _api(_service(_profile()), auth=_auth())
    assert api.dispatch("GET", "/candidates/cand-1/profile", None, None).status == 401
    # Propriétaire d'un autre candidat → 404 neutre (anti-énumération).
    assert api.dispatch("GET", "/candidates/cand-1/profile", None, _hdr("tok-other")).status == 404
    assert api.dispatch("GET", "/candidates/cand-1/profile", None, _hdr("tok-rev")).status == 200


# --- PUT ---------------------------------------------------------------------

def test_put_profile_updates_skills():
    store = FakeProfileStore(_profile(skills=["React"]))
    api = _api(ProfileService(store), auth=_auth())
    resp = api.dispatch(
        "PUT", "/candidates/cand-1/profile", {"skills": ["React", "Agile", "Scrum"]}, _hdr("tok-rev")
    )
    assert resp.status == 200
    assert set(resp.body["skills"]) >= {"React", "Agile", "Scrum"}
    assert store.get("cand-1").skills == resp.body["skills"]  # persisté


def test_put_profile_requires_reviewer():
    api = _api(_service(_profile()), auth=_auth())
    body = {"skills": ["React"]}
    assert api.dispatch("PUT", "/candidates/cand-1/profile", body, _hdr("tok-view")).status == 403
    assert api.dispatch("PUT", "/candidates/cand-1/profile", body, None).status == 401
    assert api.dispatch("PUT", "/candidates/cand-1/profile", body, _hdr("tok-rev")).status == 200


def test_put_profile_owner_gated_before_reviewer():
    # Un reviewer d'un AUTRE candidat ne doit pas distinguer « existe » de « hors périmètre ».
    api = _api(_service(_profile()), auth=_auth())
    resp = api.dispatch(
        "PUT", "/candidates/cand-1/profile", {"skills": ["React"]}, _hdr("tok-other")
    )
    assert resp.status == 404


@pytest.mark.parametrize("bad", [123, "React", None, [1, 2], ["ok", 3]])
def test_put_profile_rejects_invalid_skills(bad):
    api = _api(_service(_profile()), auth=_auth())
    resp = api.dispatch("PUT", "/candidates/cand-1/profile", {"skills": bad}, _hdr("tok-rev"))
    assert resp.status == 400


def test_put_profile_empty_skills_is_400():
    api = _api(_service(_profile()), auth=_auth())
    resp = api.dispatch("PUT", "/candidates/cand-1/profile", {"skills": []}, _hdr("tok-rev"))
    assert resp.status == 400


def test_put_profile_404_when_candidate_has_no_profile():
    api = _api(_service(), auth=_auth())  # aucun profil
    resp = api.dispatch(
        "PUT", "/candidates/cand-1/profile", {"skills": ["React"]}, _hdr("tok-rev")
    )
    assert resp.status == 404


def test_profile_unsupported_method_405():
    api = _api(_service(_profile()), auth=_auth())
    assert api.dispatch(
        "POST", "/candidates/cand-1/profile", {}, _hdr("tok-rev")
    ).status == 405
