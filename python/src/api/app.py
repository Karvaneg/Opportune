"""Dispatcher de l'API Hermes (V2, OPP-093).

``HermesApi.dispatch(method, path, body)`` route une requête vers l'orchestrateur et rend
une ``Response`` (statut + corps JSON-sérialisable), **sans dépendre du transport HTTP**.
C'est là que vit le routage ; ``server.py`` n'en est que l'adaptateur socket.

Endpoints :

    POST /candidates/{candidate_id}/recommendations   (OPP-093)
    GET  /runs/{run_id}                                (OPP-094)
    GET  /recommendations/{recommendation_id}          (OPP-094)
    POST /recommendations/{recommendation_id}/decision (OPP-094)

Le premier recommande et pré-évalue les offres du candidat, journalise l'exécution
(``run_id``) et crée des décisions ``pending`` — mais **ne déclenche aucune candidature ni
message**. Les statuts ``approved`` / ``pending_review`` / ``rejected`` sont ceux de la
**pré-évaluation automatique** (advisory), pas des décisions humaines définitives. Les
suivants consultent une exécution/recommandation et **enregistrent une décision humaine**
(approve/reject/defer), persistée et historisée.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from app.decision import Decision, decision_id
from app.decision_service import UnknownDecisionError
from app.recommendation_service import OfferRecommendation, UnknownCandidateError
from hermes.models import HermesRun
from hermes.orchestrator import HermesOrchestrator


@dataclass(frozen=True)
class Response:
    """Résultat transport-agnostique d'un appel API : statut HTTP + corps."""

    status: int
    body: dict


class ApiError(Exception):
    """Erreur portant un statut HTTP et un message client (rendus en JSON)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# Routes connues (chemin sans query string).
_RECOMMENDATIONS = re.compile(r"^/candidates/(?P<candidate_id>[^/]+)/recommendations$")
_RUN = re.compile(r"^/runs/(?P<run_id>[^/]+)$")
_RECOMMENDATION_DECISION = re.compile(r"^/recommendations/(?P<rid>[^/]+)/decision$")
_RECOMMENDATION = re.compile(r"^/recommendations/(?P<rid>[^/]+)$")

# Verbes de décision exposés par l'API → statuts de validation humaine du domaine.
_DECISION_VERBS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}


class HermesApi:
    """Adapte l'orchestrateur Hermes en une API requête → réponse, sans transport."""

    def __init__(self, orchestrator: HermesOrchestrator) -> None:
        self.orchestrator = orchestrator

    def dispatch(self, method: str, path: str, body: dict | None = None) -> Response:
        """Route ``(method, path, body)`` vers un handler ; convertit toute ``ApiError``.

        Le corps est optionnel ; la query string éventuelle est ignorée à ce stade.
        """
        path = path.split("?", 1)[0]
        try:
            return self._route(method.upper(), path, body or {})
        except ApiError as exc:
            return Response(exc.status, {"error": exc.message})
        except Exception:  # noqa: BLE001 — filet de sécurité : jamais de connexion coupée
            # Toute erreur inattendue devient un 500 propre plutôt qu'une exception non
            # gérée qui remonterait jusqu'au socket (réponse absente / connexion tuée).
            return Response(500, {"error": "erreur interne"})

    def _route(self, method: str, path: str, body: dict) -> Response:
        match = _RECOMMENDATIONS.match(path)
        if match:
            self._require(method, "POST", path)
            return self._post_recommendations(unquote(match["candidate_id"]), body)

        match = _RUN.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_run(unquote(match["run_id"]))

        match = _RECOMMENDATION_DECISION.match(path)
        if match:
            self._require(method, "POST", path)
            return self._post_decision(unquote(match["rid"]), body)

        match = _RECOMMENDATION.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_recommendation(unquote(match["rid"]))

        raise ApiError(404, f"route inconnue : {method} {path}")

    @staticmethod
    def _require(method: str, expected: str, path: str) -> None:
        if method != expected:
            raise ApiError(405, f"méthode {method} non autorisée sur {path}")

    def _post_recommendations(self, candidate_id: str, body: dict) -> Response:
        limit = body.get("limit", 10)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ApiError(400, "limit doit être un entier ≥ 0")

        # Les filtres arrivent à l'étape « filtres et pagination » : on les rejette
        # explicitement plutôt que de les ignorer en silence (le client saurait alors
        # à tort que son filtrage a été pris en compte).
        if body.get("filters"):
            raise ApiError(400, "filters non encore supporté (prévu à l'étape « filtres et pagination »)")

        # Une seule passe : run (persistance + trace) et pré-évaluation (buckets) partagent
        # la même recommandation, donc les offres présentées sont exactement celles dont la
        # décision a été persistée (une offre en erreur est tracée dans run.errors, pas
        # présentée comme évaluée).
        try:
            run, buckets = self.orchestrator.run_and_evaluate_for_candidate(
                candidate_id, limit=limit
            )
        except UnknownCandidateError:
            raise ApiError(404, f"candidat inconnu : {candidate_id}")
        except ValueError as exc:
            # Seuils incohérents / limit invalide remontés par le service : erreur client.
            raise ApiError(400, str(exc))

        approved = [self._serialize(candidate_id, r) for r in buckets["recommendations"]]
        pending = [self._serialize(candidate_id, r) for r in buckets["pending_review"]]
        rejected = [self._serialize(candidate_id, r) for r in buckets["rejected"]]
        return Response(
            200,
            {
                "run_id": run.run_id,
                "approved": approved,
                "pending_review": pending,
                "rejected": rejected,
                "evaluated_count": len(approved) + len(pending) + len(rejected),
                "errors": list(run.errors),
            },
        )

    def _get_run(self, run_id: str) -> Response:
        run = self.orchestrator.get_run(run_id)
        if run is None:
            raise ApiError(404, f"run inconnu : {run_id}")
        return Response(200, self._serialize_run(run))

    def _get_recommendation(self, recommendation_id: str) -> Response:
        decision = self.orchestrator.get_recommendation(recommendation_id)
        if decision is None:
            raise ApiError(404, f"recommandation inconnue : {recommendation_id}")
        return Response(200, self._serialize_decision(decision))

    def _post_decision(self, recommendation_id: str, body: dict) -> Response:
        verb = body.get("decision")
        # ``verb`` vient du JSON client : un tableau/objet n'est pas hashable et ferait
        # lever ``dict.get`` — on écarte tout ce qui n'est pas une chaîne connue.
        status = _DECISION_VERBS.get(verb) if isinstance(verb, str) else None
        if status is None:
            raise ApiError(
                400, "decision doit valoir approve, reject ou defer"
            )
        comment = body.get("comment")
        if comment is not None and not isinstance(comment, str):
            raise ApiError(400, "comment doit être une chaîne")
        try:
            decision = self.orchestrator.record_human_decision(
                recommendation_id, status, comment=comment
            )
        except UnknownDecisionError:
            raise ApiError(404, f"recommandation inconnue : {recommendation_id}")
        return Response(200, self._serialize_decision(decision))

    @staticmethod
    def _serialize(candidate_id: str, reco: OfferRecommendation) -> dict:
        """Représentation JSON d'une recommandation, avec un id stable réutilisable."""
        return {
            "recommendation_id": decision_id(candidate_id, reco.offer.id),
            "offer_id": reco.offer.id,
            "title": reco.offer.title,
            "company": reco.offer.company,
            "score": reco.score,
            "action": reco.action,
            "justification": reco.justification,
        }

    @staticmethod
    def _serialize_run(run: HermesRun) -> dict:
        """Représentation JSON d'une exécution journalisée."""
        return {
            "run_id": run.run_id,
            "candidate_id": run.candidate_id,
            "executed_at": run.executed_at,
            "evaluations": [
                {"offer_id": e.offer_id, "score": e.score, "decision_status": e.decision_status}
                for e in run.evaluations
            ],
            "errors": list(run.errors),
        }

    @staticmethod
    def _serialize_decision(decision: Decision) -> dict:
        """Représentation JSON d'une décision, historique inclus (recommandation d'origine préservée)."""
        return {
            "recommendation_id": decision.id,
            "candidate_id": decision.candidate_id,
            "offer_id": decision.offer_id,
            "action": decision.action,
            "score": decision.score,
            "justification": decision.justification,
            "status": decision.status,
            "comment": decision.comment,
            "history": [
                {"status": ev.status, "at": ev.at, "comment": ev.comment}
                for ev in decision.history
            ],
        }
