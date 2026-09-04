"""Dispatcher de l'API Hermes (V2, OPP-093).

``HermesApi.dispatch(method, path, body)`` route une requête vers l'orchestrateur et rend
une ``Response`` (statut + corps JSON-sérialisable), **sans dépendre du transport HTTP**.
C'est là que vit le routage ; ``server.py`` n'en est que l'adaptateur socket.

Endpoint de cette étape (OPP-093) :

    POST /candidates/{candidate_id}/recommendations

Il recommande et pré-évalue les offres du candidat, journalise l'exécution (``run_id``) et
crée des décisions ``pending`` — mais **ne déclenche aucune candidature ni message**. Les
statuts ``approved`` / ``pending_review`` / ``rejected`` sont ceux de la **pré-évaluation
automatique** (advisory), pas des décisions humaines définitives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.decision import decision_id
from app.recommendation_service import OfferRecommendation, UnknownCandidateError
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

    def _route(self, method: str, path: str, body: dict) -> Response:
        match = _RECOMMENDATIONS.match(path)
        if match:
            if method != "POST":
                raise ApiError(405, f"méthode {method} non autorisée sur {path}")
            return self._post_recommendations(match["candidate_id"], body)
        raise ApiError(404, f"route inconnue : {method} {path}")

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
