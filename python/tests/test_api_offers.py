"""Tests de l'endpoint d'intake d'offre collée (OPP-145).

L'intake LLM est **injecté** (faux) : aucun réseau, aucun Ollama. On vérifie le contrat
HTTP (validation, sérialisation, mapping d'erreurs, garde reviewer, route optionnelle).
"""

import pytest

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.llm_client import LLMError
from app.offer import Offer
from app.offer_analysis import OfferAnalysisError
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from app.url_fetch import EmptyContentError, UnsupportedUrlError, UrlUnreachableError
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


def _api_url(offer_url_intake, *, offer_intake=None, auth=None) -> HermesApi:
    """API montée avec l'intake par URL (OPP-148), et éventuellement l'intake texte."""
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(
        orchestrator, auth=auth, offer_intake=offer_intake, offer_url_intake=offer_url_intake
    )


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
        "seniority", "contract_type", "summary", "source", "url", "created_at", "kind",
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


def test_offers_unsupported_method_405():
    # GET (catalogue) et POST (intake) sont montés ; toute autre méthode → 405.
    assert _api(lambda *a, **k: _offer()).dispatch("PUT", "/offers", None, None).status == 405


def test_post_offers_requires_reviewer_role():
    # Même périmètre (cand-1), rôle différent : sans reviewer → 403, avec → 201.
    viewer = _api(
        lambda raw_text, *, source, url="": _offer(),
        auth=LocalAuthProvider(User("moi", "viewer", frozenset({"cand-1"}))),
    )
    assert viewer.dispatch("POST", "/offers", {"text": "x"}).status == 403
    reviewer = _api(
        lambda raw_text, *, source, url="": _offer(),
        auth=LocalAuthProvider(User("moi", REVIEWER, frozenset({"cand-1"}))),
    )
    assert reviewer.dispatch("POST", "/offers", {"text": "x"}).status == 201


# --- Voie URL (OPP-148) ------------------------------------------------------

def test_post_offers_by_url_creates_and_serializes():
    captured = {}

    def url_intake(url, *, source):
        captured.update(url=url, source=source)
        return _offer(title="Data Engineer", url=url)

    resp = _api_url(url_intake).dispatch(
        "POST", "/offers", {"url": "https://example.com/jobs/42"}, None
    )
    assert resp.status == 201
    assert resp.body["title"] == "Data Engineer"
    # Source par défaut = domaine de l'URL (utile au catalogue).
    assert captured["source"] == "example.com"
    assert captured["url"] == "https://example.com/jobs/42"


def test_post_offers_url_explicit_source_kept():
    seen = {}

    def url_intake(url, *, source):
        seen.update(source=source)
        return _offer()

    _api_url(url_intake).dispatch(
        "POST", "/offers", {"url": "https://x.io/o", "source": "welcometothejungle"}, None
    )
    assert seen["source"] == "welcometothejungle"


def test_post_offers_text_takes_precedence_over_url():
    calls = {"text": 0, "url": 0}

    def text_intake(raw_text, *, source, url=""):
        calls["text"] += 1
        return _offer()

    def url_intake(url, *, source):
        calls["url"] += 1
        return _offer()

    _api_url(url_intake, offer_intake=text_intake).dispatch(
        "POST", "/offers", {"text": "coller", "url": "https://x.io/o"}, None
    )
    assert calls == {"text": 1, "url": 0}


def test_post_offers_neither_text_nor_url_400():
    assert _api_url(lambda *a, **k: _offer()).dispatch("POST", "/offers", {}, None).status == 400


def test_post_offers_url_unsupported_is_400():
    def url_intake(url, *, source):
        raise UnsupportedUrlError("cible interne refusée")

    resp = _api_url(url_intake).dispatch("POST", "/offers", {"url": "http://127.0.0.1/x"}, None)
    assert resp.status == 400


@pytest.mark.parametrize("err", [UrlUnreachableError("404"), EmptyContentError("vide")])
def test_post_offers_url_fetch_failure_is_502(err):
    def url_intake(url, *, source):
        raise err

    resp = _api_url(url_intake).dispatch("POST", "/offers", {"url": "https://x.io/o"}, None)
    assert resp.status == 502


def test_post_offers_url_absent_without_url_intake_404():
    # Intake texte câblé mais pas l'intake URL : une requête URL seule → 404 neutre.
    api = _api(lambda raw_text, *, source, url="": _offer())  # offer_url_intake absent
    assert api.dispatch("POST", "/offers", {"url": "https://x.io/o"}, None).status == 404
