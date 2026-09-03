"""Tests du dispatcher de l'API Hermes (OPP-093).

On teste ``HermesApi.dispatch`` directement (aucun réseau) avec de vrais dépôts SQLite en
mémoire. Un test d'intégration socket couvre en plus l'adaptateur HTTP (``api.server``)
pour l'en-tête ``Content-Length`` invalide.
"""

import itertools
import socket
import threading

import pytest

from api.app import HermesApi
from api.server import create_server
from app.candidate_profile import create_profile
from app.db import connect
from app.decision import decision_id
from app.decision_service import DecisionService
from app.decision_store import DecisionStore
from app.offer import Offer
from app.offer_store import OfferStore
from app.profile_store import ProfileStore
from app.recommendation_service import RecommendationService
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
    run_ids = (f"run-{n}" for n in itertools.count(1))
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        DecisionService(decisions, now=lambda: "2026-09-04T00:00:00+00:00"),
        runs=runs,
        run_id=lambda: next(run_ids),
        now=lambda: "2026-09-04T12:00:00+00:00",
    )
    yield HermesApi(orchestrator), offers, decisions, runs
    conn.close()


def _seed_one_per_bucket(offers):
    offers.save(_offer(id="off-app", title="App", url="http://app"))  # 100 → approved
    offers.save(_offer(id="off-pend", title="Pend", url="http://pend",
                       skills=["Python", "Java"], location="Lyon"))  # 68 → pending
    offers.save(_offer(id="off-rej", title="Rej", url="http://rej",
                       skills=["Cobol"], contract_type="Freelance",
                       location="Lyon", seniority="Lead"))  # 0 → rejected


def test_post_recommendations_returns_buckets_and_run_id(env):
    api, offers, decisions, runs = env
    _seed_one_per_bucket(offers)

    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})

    assert resp.status == 200
    assert resp.body["run_id"] == "run-1"
    assert resp.body["evaluated_count"] == 3
    assert [r["offer_id"] for r in resp.body["approved"]] == ["off-app"]
    assert [r["offer_id"] for r in resp.body["pending_review"]] == ["off-pend"]
    assert [r["offer_id"] for r in resp.body["rejected"]] == ["off-rej"]
    assert resp.body["errors"] == []  # aucune offre en erreur
    # Trace et décisions persistées (mais rien de plus : pas de candidature).
    assert runs.get("run-1") is not None
    assert decisions.count() == 3


def test_recommendation_payload_shape(env):
    api, offers, _, _ = env
    offers.save(_offer(id="off-app", title="App", company="Acme", url="http://app"))
    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    reco = resp.body["approved"][0]
    assert reco["recommendation_id"] == decision_id("cand-1", "off-app")
    assert reco["offer_id"] == "off-app"
    assert reco["title"] == "App"
    assert reco["company"] == "Acme"
    assert reco["score"] == 100
    assert reco["action"] == "postuler"
    assert "Score 100/100" in reco["justification"]


def test_default_limit_when_absent(env):
    api, offers, _, _ = env
    _seed_one_per_bucket(offers)
    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {})
    assert resp.status == 200
    assert resp.body["evaluated_count"] == 3


def test_unknown_candidate_returns_404(env):
    api, _, _, runs = env
    resp = api.dispatch("POST", "/candidates/nope/recommendations", {"limit": 5})
    assert resp.status == 404
    assert "candidat inconnu" in resp.body["error"]
    assert runs.count() == 0  # aucun run enregistré


def test_filters_not_supported_yet_returns_400(env):
    api, offers, _, runs = env
    _seed_one_per_bucket(offers)
    resp = api.dispatch(
        "POST", "/candidates/cand-1/recommendations",
        {"limit": 10, "filters": {"contract_type": "freelance"}},
    )
    assert resp.status == 400
    assert "filters" in resp.body["error"]
    assert runs.count() == 0  # rien exécuté


def test_invalid_limit_returns_400(env):
    api, _, _, _ = env
    for bad in (-1, "20", True):
        resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": bad})
        assert resp.status == 400
        assert "limit" in resp.body["error"]


def test_wrong_method_returns_405(env):
    api, _, _, _ = env
    resp = api.dispatch("GET", "/candidates/cand-1/recommendations", {})
    assert resp.status == 405


def test_unknown_route_returns_404(env):
    api, _, _, _ = env
    resp = api.dispatch("POST", "/unknown", {})
    assert resp.status == 404
    assert "route inconnue" in resp.body["error"]


def test_query_string_is_ignored(env):
    api, offers, _, _ = env
    _seed_one_per_bucket(offers)
    resp = api.dispatch("POST", "/candidates/cand-1/recommendations?debug=1", {"limit": 10})
    assert resp.status == 200


class _FailingDecide:
    """Décore un DecisionService : ``decide`` échoue pour certaines offres, ``evaluate`` reste réel."""

    def __init__(self, real: DecisionService, failing_offer_ids: set[str]) -> None:
        self._real = real
        self._failing = set(failing_offer_ids)

    def decide(self, recommendation, candidate_id):
        if recommendation.offer.id in self._failing:
            raise RuntimeError("échec simulé")
        return self._real.decide(recommendation, candidate_id)

    def evaluate(self, recommendation):
        return self._real.evaluate(recommendation)


def test_offer_error_is_reported_and_excluded_from_buckets(env):
    api, offers, decisions, _ = env
    _seed_one_per_bucket(offers)
    # decide() échoue pour l'offre approuvée : elle doit être tracée dans "errors" et
    # absente des buckets (jamais présentée comme évaluée), les autres passant normalement.
    api.orchestrator.decisions = _FailingDecide(api.orchestrator.decisions, {"off-app"})

    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})

    assert resp.status == 200
    assert [r["offer_id"] for r in resp.body["approved"]] == []  # exclue du résultat
    assert [r["offer_id"] for r in resp.body["pending_review"]] == ["off-pend"]
    assert [r["offer_id"] for r in resp.body["rejected"]] == ["off-rej"]
    assert resp.body["evaluated_count"] == 2  # seules les offres persistées comptent
    assert len(resp.body["errors"]) == 1
    assert resp.body["errors"][0].startswith("off-app: ")
    # La décision de l'offre en erreur n'est pas persistée.
    assert decisions.get(decision_id("cand-1", "off-app")) is None


@pytest.fixture
def http_address(env):
    """Démarre le vrai serveur HTTP (séquentiel) sur un port libre, dans un thread."""
    api = env[0]
    server = create_server(api, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _raw_response(address, request: bytes) -> str:
    host, port = address
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(request)
        chunks = []
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    return b"".join(chunks).decode("utf-8", "replace")


def test_invalid_content_length_returns_400(http_address):
    # En-tête présent mais non numérique : l'adaptateur doit répondre 400 proprement,
    # sans laisser ``int()`` lever une exception non capturée (500).
    request = (
        b"POST /candidates/cand-1/recommendations HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Content-Length: abc\r\n"
        b"\r\n"
    )
    response = _raw_response(http_address, request)
    status_line = response.split("\r\n", 1)[0]
    assert " 400 " in status_line, status_line
    assert "Content-Length invalide" in response
