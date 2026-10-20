"""Tests de l'endpoint de collecte d'offres réelles (POST /collect, OPP-167).

Le collector est **injecté** (faux) : aucun réseau, aucun Adzuna, aucun Ollama. On vérifie
le contrat HTTP : sérialisation du bilan, plafonnement de ``max``, validation des critères,
garde reviewer, route optionnelle, et remontée d'une erreur source dans le corps (pas le statut).
"""

import pytest

from api.app import _COLLECT_MAX_CAP, _COLLECT_MAX_DEFAULT, HermesApi
from app.auth import REVIEWER, AuthProvider, User
from app.db import connect
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer_collection import CollectionFailure, CollectionReport
from app.offer_source import RawOffer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
from hermes.orchestrator import HermesOrchestrator
from hermes.run_store import RunStore


def _report(**overrides) -> CollectionReport:
    data = dict(collected=3, stored=2, duplicates=1, failures=(), source_error=None)
    data.update(overrides)
    return CollectionReport(**data)


def _api(collector, *, auth=None) -> HermesApi:
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    return HermesApi(orchestrator, auth=auth, collector=collector)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_post_collect_serializes_enrichment_counts():
    # OPP-169 : les compteurs d'enrichissement non nuls remontent bien dans le bilan JSON.
    def collector(*, what, where, max_offers):
        return _report(collected=4, stored=4, duplicates=0, enriched=2, enriched_recovered=1)

    resp = _api(collector).dispatch("POST", "/collect", {"what": "dev"}, None)
    assert resp.status == 200
    assert resp.body["enriched"] == 2
    assert resp.body["enriched_recovered"] == 1


def test_post_collect_runs_and_serializes_report():
    captured = {}

    def collector(*, what, where, max_offers):
        captured.update(what=what, where=where, max_offers=max_offers)
        return _report(collected=5, stored=3, duplicates=2)

    resp = _api(collector).dispatch(
        "POST", "/collect", {"what": "python", "where": "Paris"}, None
    )
    assert resp.status == 200
    assert resp.body == {
        "collected": 5,
        "stored": 3,
        "duplicates": 2,
        "failures": 0,
        "source_error": None,
        "enriched": 0,
        "enriched_recovered": 0,
    }
    # enriched / enriched_recovered présents (OPP-169), à 0 ici.
    assert resp.body["enriched"] == 0 and resp.body["enriched_recovered"] == 0

    # Critères transmis tels quels ; ``max`` prend le défaut quand il est absent.
    assert captured == {"what": "python", "where": "Paris", "max_offers": _COLLECT_MAX_DEFAULT}


def test_post_collect_defaults_empty_criteria():
    captured = {}

    def collector(*, what, where, max_offers):
        captured.update(what=what, where=where)
        return _report()

    _api(collector).dispatch("POST", "/collect", {}, None)
    assert captured == {"what": "", "where": ""}


def test_post_collect_strips_criteria():
    captured = {}

    def collector(*, what, where, max_offers):
        captured.update(what=what, where=where)
        return _report()

    _api(collector).dispatch("POST", "/collect", {"what": "  data  ", "where": " Lyon "}, None)
    assert captured == {"what": "data", "where": "Lyon"}


def test_post_collect_clamps_max_to_cap():
    captured = {}

    def collector(*, what, where, max_offers):
        captured["max_offers"] = max_offers
        return _report()

    _api(collector).dispatch("POST", "/collect", {"max": 10_000}, None)
    assert captured["max_offers"] == _COLLECT_MAX_CAP


def test_post_collect_honours_explicit_max_below_cap():
    captured = {}

    def collector(*, what, where, max_offers):
        captured["max_offers"] = max_offers
        return _report()

    _api(collector).dispatch("POST", "/collect", {"max": 7}, None)
    assert captured["max_offers"] == 7


@pytest.mark.parametrize("bad", [0, -1, True, "20", 3.5])
def test_post_collect_rejects_invalid_max(bad):
    api = _api(lambda **k: _report())
    assert api.dispatch("POST", "/collect", {"max": bad}, None).status == 400


@pytest.mark.parametrize("key", ["what", "where"])
def test_post_collect_rejects_non_string_criteria(key):
    api = _api(lambda **k: _report())
    assert api.dispatch("POST", "/collect", {key: 123}, None).status == 400


def test_post_collect_source_error_is_reported_in_body_not_status():
    # Panne de la source (identifiants Adzuna manquants, quota…) : le collector rend un bilan
    # porteur de ``source_error`` ; l'API répond 200 avec le détail, pas un statut d'erreur.
    report = _report(collected=0, stored=0, duplicates=0, source_error="AdzunaAuthError: …")
    resp = _api(lambda **k: report).dispatch("POST", "/collect", {}, None)
    assert resp.status == 200
    assert resp.body["source_error"] == "AdzunaAuthError: …"
    assert resp.body["stored"] == 0


def test_post_collect_counts_failures():
    failures = (
        CollectionFailure(raw=RawOffer(source="adzuna", raw_text="x", url="u1"), error="boom"),
        CollectionFailure(raw=RawOffer(source="adzuna", raw_text="y", url="u2"), error="bam"),
    )
    report = _report(collected=4, stored=1, duplicates=1, failures=failures)
    resp = _api(lambda **k: report).dispatch("POST", "/collect", {}, None)
    assert resp.body["failures"] == 2


def test_collect_route_absent_without_collector():
    conn = connect(":memory:")
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        DecisionService(DecisionStore(conn)),
        runs=RunStore(conn),
    )
    api = HermesApi(orchestrator)  # pas de collector → route non montée
    assert api.dispatch("POST", "/collect", {}, None).status == 404


def test_collect_unsupported_method_405():
    assert _api(lambda **k: _report()).dispatch("GET", "/collect", None, None).status == 405


def test_post_collect_requires_reviewer_role():
    auth = AuthProvider({
        "tok-rev": User("rev", REVIEWER, frozenset({"cand-1"})),
        "tok-view": User("view", "viewer", frozenset({"cand-1"})),
    })
    api = _api(lambda **k: _report(), auth=auth)
    assert api.dispatch("POST", "/collect", {}, _hdr("tok-view")).status == 403
    assert api.dispatch("POST", "/collect", {}, _hdr("tok-rev")).status == 200
    assert api.dispatch("POST", "/collect", {}, None).status == 401
