"""Tests de l'endpoint d'intake d'offre collée (OPP-145).

L'intake LLM est **injecté** (faux) : aucun réseau, aucun Ollama. On vérifie le contrat
HTTP (validation, sérialisation, mapping d'erreurs, garde reviewer, route optionnelle).
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, AuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.llm_client import LLMError
from app.offer import Offer
from app.offer_analysis import OfferAnalysisError
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _offer(**overrides) -> Offer:
    data = dict(
        id="o-1", title="Dev", company="Acme", location="Paris", skills=["Python"],
        seniority="Senior", contract_type="CDI", summary="s", attention_points=[],
        source="collée", url="", raw_text="brut",
    )
    data.update(overrides)
    return Offer(**data)


def _api(offer_intake, *, auth=None) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=auth, offer_intake=offer_intake)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_post_offers_creates_and_serializes():
    captured = {}

    def intake(raw_text, *, source, url=""):
        captured.update(raw_text=raw_text, source=source, url=url)
        return _offer(title="Data Engineer", raw_text=raw_text)

    resp = _api(intake).dispatch("POST", "/offers", {"text": "Nous recrutons un Data Engineer…"}, None)
    assert resp.status == 201
    assert resp.body["title"] == "Data Engineer"
    assert resp.body["id"] == "o-1"
    assert set(resp.body) == {
        "id", "title", "company", "location", "skills",
        "seniority", "contract_type", "summary", "source", "url", "created_at",
    }
    # Le texte est transmis tel quel ; source par défaut « collée ».
    assert captured["raw_text"].startswith("Nous recrutons")
    assert captured["source"] == "collée"


def test_post_offers_passes_source_and_url():
    seen = {}

    def intake(raw_text, *, source, url=""):
        seen.update(source=source, url=url)
        return _offer()

    _api(intake).dispatch("POST", "/offers", {"text": "x", "source": "linkedin", "url": "http://o"}, None)
    assert seen == {"source": "linkedin", "url": "http://o"}


@pytest.mark.parametrize("body", [{}, {"text": "   "}, {"text": 123}])
def test_post_offers_rejects_empty_or_non_string_text(body):
    api = _api(lambda *a, **k: _offer())
    assert api.dispatch("POST", "/offers", body, None).status == 400


def test_post_offers_maps_value_error_to_400():
    def intake(raw_text, *, source, url=""):
        raise ValueError("texte trop court")

    assert _api(intake).dispatch("POST", "/offers", {"text": "x"}, None).status == 400


def test_post_offers_maps_analysis_error_to_502():
    def intake(raw_text, *, source, url=""):
        raise OfferAnalysisError("json invalide")

    assert _api(intake).dispatch("POST", "/offers", {"text": "x"}, None).status == 502


def test_post_offers_maps_llm_error_to_502():
    def intake(raw_text, *, source, url=""):
        raise LLMError("ollama injoignable")

    assert _api(intake).dispatch("POST", "/offers", {"text": "x"}, None).status == 502


def test_offers_route_absent_without_intake():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator)  # pas d'offer_intake → route non montée
    assert api.dispatch("POST", "/offers", {"text": "x"}, None).status == 404


def test_post_offers_wrong_method_405():
    assert _api(lambda *a, **k: _offer()).dispatch("GET", "/offers", None, None).status == 405


def test_post_offers_requires_reviewer_role():
    auth = AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-view": User("view", "viewer", frozenset({"cand-1"})),
    })
    api = _api(lambda raw_text, *, source, url="": _offer(), auth=auth)
    assert api.dispatch("POST", "/offers", {"text": "x"}, _hdr("tok-view")).status == 403
    assert api.dispatch("POST", "/offers", {"text": "x"}, _hdr("tok-rev")).status == 201
    assert api.dispatch("POST", "/offers", {"text": "x"}, None).status == 401
