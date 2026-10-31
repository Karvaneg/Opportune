"""Tests des routes de profil candidat (GET/PUT /candidates/{id}/profile, OPP-158).

Service profil réel adossé à un dépôt factice : on vérifie le contrat HTTP — sérialisation,
garde propriétaire (404 neutre hors périmètre), garde reviewer sur l'édition, validation du
corps, profil absent rendu **vide en 200** (OPP-195), route optionnelle, et méthode non supportée.
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User
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


def _auth() -> LocalAuthProvider:
    # Identité locale par défaut des tests : propriétaire reviewer de cand-1.
    return LocalAuthProvider(User("moi", REVIEWER, frozenset({"cand-1"})))


# --- GET ---------------------------------------------------------------------

def test_get_profile_serializes_fields():
    api = _api(_service(_profile(skills=["React", "HTML5"])))
    resp = api.dispatch("GET", "/candidates/cand-1/profile", None, None)
    assert resp.status == 200
    assert resp.body["id"] == "cand-1"
    assert resp.body["name"] == "Marie"
    assert resp.body["skills"] == ["React", "HTML5"]
    assert resp.body["contract_type"] == "CDI"
    # Parcours vide par défaut (OPP-176) : la clé existe toujours pour un front stable.
    assert resp.body["experiences"] == []


def test_get_profile_serializes_experiences():
    # OPP-176 : le parcours extrait du CV (OPP-173) est exposé au front pour affichage.
    exp = {
        "title": "Développeuse Fullstack",
        "company": "CBNSA",
        "period": "2023 – 2025",
        "location": "Gironde",
        "highlights": ["Refonte d'un portail Symfony", "+45 % de trafic organique"],
        "skills": ["Symfony", "PostgreSQL"],
    }
    profile = create_profile(
        id="cand-1", name="Marie", skills=["React"], contract_type="CDI",
        experiences=[exp],
    )
    api = _api(_service(profile))
    resp = api.dispatch("GET", "/candidates/cand-1/profile", None, None)
    assert resp.status == 200
    assert resp.body["experiences"] == [exp]


def test_get_profile_returns_empty_200_when_candidate_has_no_profile():
    # Candidat accessible mais sans profil encore (recherche neuve) : 200 avec un profil **vide**,
    # pas un 404 (OPP-195). Un profil pas encore créé est un état normal, pas une erreur — le front
    # affiche l'import CV et la console ne se salit pas d'un 404 rouge.
    api = _api(_service())  # aucun profil enregistré

    resp = api.dispatch("GET", "/candidates/cand-1/profile", None, None)

    assert resp.status == 200
    assert resp.body["skills"] == []
    assert resp.body["experiences"] == []
    assert resp.body["name"] == ""


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
    # Propriétaire d'un autre candidat → 404 neutre (anti-énumération).
    foreign = _api(
        _service(_profile()),
        auth=LocalAuthProvider(User("autre", REVIEWER, frozenset({"cand-2"}))),
    )
    assert foreign.dispatch("GET", "/candidates/cand-1/profile", None, None).status == 404
    owner = _api(_service(_profile()), auth=_auth())
    assert owner.dispatch("GET", "/candidates/cand-1/profile", None, None).status == 200


# --- PUT ---------------------------------------------------------------------

def test_put_profile_updates_skills():
    store = FakeProfileStore(_profile(skills=["React"]))
    api = _api(ProfileService(store), auth=_auth())
    resp = api.dispatch(
        "PUT", "/candidates/cand-1/profile", {"skills": ["React", "Agile", "Scrum"]}
    )
    assert resp.status == 200
    assert set(resp.body["skills"]) >= {"React", "Agile", "Scrum"}
    assert store.get("cand-1").skills == resp.body["skills"]  # persisté


def test_put_profile_requires_reviewer():
    body = {"skills": ["React"]}
    # Propriétaire sans le rôle reviewer → 403.
    viewer = _api(
        _service(_profile()),
        auth=LocalAuthProvider(User("moi", "viewer", frozenset({"cand-1"}))),
    )
    assert viewer.dispatch("PUT", "/candidates/cand-1/profile", body).status == 403
    # Propriétaire reviewer → 200.
    owner = _api(_service(_profile()), auth=_auth())
    assert owner.dispatch("PUT", "/candidates/cand-1/profile", body).status == 200


def test_put_profile_owner_gated_before_reviewer():
    # Un reviewer d'un AUTRE candidat ne doit pas distinguer « existe » de « hors périmètre ».
    foreign = _api(
        _service(_profile()),
        auth=LocalAuthProvider(User("autre", REVIEWER, frozenset({"cand-2"}))),
    )
    resp = foreign.dispatch("PUT", "/candidates/cand-1/profile", {"skills": ["React"]})
    assert resp.status == 404


@pytest.mark.parametrize("bad", [123, "React", None, [1, 2], ["ok", 3]])
def test_put_profile_rejects_invalid_skills(bad):
    api = _api(_service(_profile()), auth=_auth())
    resp = api.dispatch("PUT", "/candidates/cand-1/profile", {"skills": bad})
    assert resp.status == 400


def test_put_profile_empty_skills_is_400():
    api = _api(_service(_profile()), auth=_auth())
    resp = api.dispatch("PUT", "/candidates/cand-1/profile", {"skills": []})
    assert resp.status == 400


def test_put_profile_404_when_candidate_has_no_profile():
    api = _api(_service(), auth=_auth())  # aucun profil
    resp = api.dispatch(
        "PUT", "/candidates/cand-1/profile", {"skills": ["React"]}
    )
    assert resp.status == 404


def test_profile_unsupported_method_405():
    api = _api(_service(_profile()), auth=_auth())
    assert api.dispatch(
        "POST", "/candidates/cand-1/profile", {}
    ).status == 405
