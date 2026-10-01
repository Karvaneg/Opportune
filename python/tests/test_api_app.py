"""Tests du dispatcher de l'API Hermes (OPP-093).

On teste ``HermesApi.dispatch`` directement (aucun réseau) avec de vrais dépôts SQLite en
mémoire. Un test d'intégration socket couvre en plus l'adaptateur HTTP (``api.server``)
pour l'en-tête ``Content-Length`` invalide.
"""

import itertools
import json
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


def test_post_recommendations_returns_items_and_run_id(env):
    api, offers, decisions, runs = env
    _seed_one_per_bucket(offers)

    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})

    assert resp.status == 200
    assert resp.body["run_id"] == "run-1"
    assert resp.body["total"] == 3
    # Items à plat, classés par score décroissant (plus de buckets dans la réponse POST).
    assert [r["offer_id"] for r in resp.body["items"]] == ["off-app", "off-pend", "off-rej"]
    assert [r["advisory_status"] for r in resp.body["items"]] == [
        "approved", "pending", "rejected"
    ]
    assert resp.body["errors"] == []  # aucune offre en erreur
    # Trace et décisions persistées (mais rien de plus : pas de candidature).
    assert runs.get("run-1") is not None
    assert decisions.count() == 3


def test_recommendation_payload_shape(env):
    api, offers, _, _ = env
    offers.save(_offer(id="off-app", title="App", company="Acme", url="http://app"))
    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 10})
    reco = resp.body["items"][0]
    assert reco["recommendation_id"] == decision_id("cand-1", "off-app")
    assert reco["offer_id"] == "off-app"
    assert reco["title"] == "App"
    assert reco["company"] == "Acme"
    assert reco["score"] == 100
    assert reco["action"] == "postuler"
    assert reco["advisory_status"] == "approved"
    assert reco["decision_status"] == "pending"  # photo initiale, pas encore validée
    assert "Score 100/100" in reco["justification"]


def test_default_limit_when_absent(env):
    api, offers, _, _ = env
    _seed_one_per_bucket(offers)
    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {})
    assert resp.status == 200
    assert resp.body["total"] == 3


def test_unknown_candidate_returns_404(env):
    api, _, _, runs = env
    resp = api.dispatch("POST", "/candidates/nope/recommendations", {"limit": 5})
    assert resp.status == 404
    assert "candidat inconnu" in resp.body["error"]
    assert runs.count() == 0  # aucun run enregistré


def test_unknown_filter_key_returns_400(env):
    api, offers, _, runs = env
    _seed_one_per_bucket(offers)
    # Clé de filtre inconnue : rejet strict (ne jamais ignorer un filtre en silence).
    resp = api.dispatch(
        "POST", "/candidates/cand-1/recommendations",
        {"limit": 10, "filters": {"seniority": "Lead"}},
    )
    assert resp.status == 400
    assert "inconnu" in resp.body["error"]
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


# --- OPP-150 : re-score ciblé d'une offre --------------------------------------


def test_rescore_offer_returns_live_decision(env):
    api, offers, decisions, _ = env
    offers.save(_offer(id="off-app", title="App", company="Acme", url="http://app"))
    resp = api.dispatch("POST", "/candidates/cand-1/offers/off-app/rescore", {})
    assert resp.status == 200
    assert resp.body["offer_id"] == "off-app"
    assert resp.body["score"] == 100
    assert resp.body["status"] == "pending"
    assert resp.body["title"] == "App"  # titre résolu depuis l'offre (sérialisation décision)
    assert decisions.get(decision_id("cand-1", "off-app")) is not None  # persistée


def test_rescore_unknown_offer_returns_404(env):
    api, _, _, _ = env
    resp = api.dispatch("POST", "/candidates/cand-1/offers/nope/rescore", {})
    assert resp.status == 404


def test_rescore_unknown_candidate_returns_404(env):
    api, offers, _, _ = env
    offers.save(_offer(id="off-app", url="http://app"))
    resp = api.dispatch("POST", "/candidates/nope/offers/off-app/rescore", {})
    assert resp.status == 404


def test_rescore_wrong_method_returns_405(env):
    api, _, _, _ = env
    resp = api.dispatch("GET", "/candidates/cand-1/offers/off-app/rescore", {})
    assert resp.status == 405


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

    def list_for_candidate(self, candidate_id):
        return self._real.list_for_candidate(candidate_id)


def test_offer_error_is_reported_and_excluded_from_items(env):
    api, offers, decisions, _ = env
    _seed_one_per_bucket(offers)
    # decide() échoue pour l'offre approuvée : elle doit être tracée dans "errors" et
    # absente des items (jamais présentée comme évaluée), les autres passant normalement.
    api.orchestrator.decisions = _FailingDecide(api.orchestrator.decisions, {"off-app"})

    resp = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})

    assert resp.status == 200
    assert [r["offer_id"] for r in resp.body["items"]] == ["off-pend", "off-rej"]
    assert resp.body["total"] == 2  # seules les offres persistées comptent
    assert len(resp.body["errors"]) == 1
    assert resp.body["errors"][0].startswith("off-app: ")
    # La décision de l'offre en erreur n'est pas persistée.
    assert decisions.get(decision_id("cand-1", "off-app")) is None


def test_errors_field_present_and_json_serializable(env):
    api, offers, _, _ = env
    _seed_one_per_bucket(offers)

    # Run sain : ``errors`` présent et vide, réponse JSON-sérialisable de bout en bout
    # (le serveur la renvoie telle quelle sur le socket).
    ok = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})
    assert ok.body["errors"] == []
    assert json.loads(json.dumps(ok.body))["errors"] == []

    # Run avec une offre en échec : ``errors`` est une liste de chaînes, fidèlement
    # sérialisée (round-trip JSON identique). Le run ne traitant que les offres **nouvelles**
    # (only_new, OPP-150), on introduit une offre fraîche dont le ``decide`` échoue — les
    # offres du premier run sont déjà décidées, donc exclues.
    offers.save(_offer(id="off-new", title="New", url="http://new"))
    api.orchestrator.decisions = _FailingDecide(api.orchestrator.decisions, {"off-new"})
    ko = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})
    assert isinstance(ko.body["errors"], list)
    assert all(isinstance(e, str) for e in ko.body["errors"])
    round_tripped = json.loads(json.dumps(ko.body))
    assert round_tripped["errors"] == ko.body["errors"]
    assert round_tripped["errors"][0].startswith("off-new: ")


def test_empty_run_is_not_persisted(env):
    # OPP-150 : relancer une analyse sans nouvelle offre (ni erreur) ne doit pas créer un
    # run vide dans la liste. Le 1er run consomme tout ; le 2e est vide → non persisté.
    api, offers, _, runs = env
    _seed_one_per_bucket(offers)
    first = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})
    assert runs.get(first.body["run_id"]) is not None

    empty = api.dispatch("POST", "/candidates/cand-1/recommendations", {"limit": 20})
    assert empty.body["total"] == 0
    assert empty.body["errors"] == []
    assert runs.get(empty.body["run_id"]) is None  # run vide non tracé


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
