"""Dispatcher de l'API Hermes (V2, OPP-093).

``HermesApi.dispatch(method, path, body)`` route une requête vers l'orchestrateur et rend
une ``Response`` (statut + corps JSON-sérialisable), **sans dépendre du transport HTTP**.
C'est là que vit le routage ; ``server.py`` n'en est que l'adaptateur socket.

Endpoints :

    POST /candidates/{candidate_id}/recommendations   (OPP-093, filtres OPP-095)
    GET  /runs/{run_id}                                (OPP-094)
    GET  /runs/{run_id}/recommendations                (OPP-095, paginé + filtres)
    GET  /recommendations/{recommendation_id}          (OPP-094)
    POST /recommendations/{recommendation_id}/decision (OPP-094)

Le POST recommande et pré-évalue les offres du candidat (filtrables via ``filters`` :
``contract_type`` exact, ``skills`` en ALL), journalise l'exécution (``run_id``, snapshot
riche par offre) et crée des décisions ``pending`` — mais **ne déclenche aucune candidature
ni message**. Il renvoie les items du run (``total`` = nb d'offres évaluées après filtres) ;
la consultation détaillée se fait paginée via ``GET /runs/{run_id}/recommendations``.

``advisory_status`` (``approved`` / ``pending`` / ``rejected``) est la **pré-évaluation
automatique** figée ; ``decision_status`` est l'**état de validation humaine courant**
(relu en direct). Les endpoints de décision **enregistrent une décision humaine**
(approve/reject/defer), persistée et historisée.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote

from app.decision import VALIDATION_STATUSES, Decision, decision_id
from app.decision_service import PRE_EVALUATION_STATUSES, UnknownDecisionError
from app.offer_normalization import normalize_contract, normalize_skills
from app.recommendation_service import UnknownCandidateError
from hermes.models import HermesRun, OfferEvaluation
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
_RUN_RECOMMENDATIONS = re.compile(r"^/runs/(?P<run_id>[^/]+)/recommendations$")
_RUN = re.compile(r"^/runs/(?P<run_id>[^/]+)$")
_RECOMMENDATION_DECISION = re.compile(r"^/recommendations/(?P<rid>[^/]+)/decision$")
_RECOMMENDATION = re.compile(r"^/recommendations/(?P<rid>[^/]+)$")

# Verbes de décision exposés par l'API → statuts de validation humaine du domaine.
_DECISION_VERBS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}

# Clés de filtre acceptées par POST /recommendations (toute autre clé → 400 explicite).
_ALLOWED_FILTER_KEYS = {"contract_type", "skills"}


class HermesApi:
    """Adapte l'orchestrateur Hermes en une API requête → réponse, sans transport."""

    def __init__(self, orchestrator: HermesOrchestrator) -> None:
        self.orchestrator = orchestrator

    def dispatch(self, method: str, path: str, body: dict | None = None) -> Response:
        """Route ``(method, path, body)`` vers un handler ; convertit toute ``ApiError``.

        Le corps est optionnel ; la query string éventuelle est parsée et transmise aux
        handlers qui l'exploitent (pagination et filtres de la consultation d'un run).
        """
        path_only, _, query_string = path.partition("?")
        query = parse_qs(query_string)
        try:
            return self._route(method.upper(), path_only, body or {}, query)
        except ApiError as exc:
            return Response(exc.status, {"error": exc.message})
        except Exception:  # noqa: BLE001 — filet de sécurité : jamais de connexion coupée
            # Toute erreur inattendue devient un 500 propre plutôt qu'une exception non
            # gérée qui remonterait jusqu'au socket (réponse absente / connexion tuée).
            return Response(500, {"error": "erreur interne"})

    def _route(self, method: str, path: str, body: dict, query: dict) -> Response:
        match = _RECOMMENDATIONS.match(path)
        if match:
            self._require(method, "POST", path)
            return self._post_recommendations(unquote(match["candidate_id"]), body)

        match = _RUN_RECOMMENDATIONS.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_run_recommendations(unquote(match["run_id"]), query)

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
        filters = self._parse_filters(body.get("filters"))

        # Une seule passe : le run persiste et trace exactement les offres retenues par les
        # filtres (une offre en erreur est tracée dans run.errors, pas présentée). Le run
        # fige un snapshot riche par offre → les items renvoyés en sont la sérialisation
        # directe (pas de re-calcul), consultables ensuite paginés via GET.
        try:
            run = self.orchestrator.run_and_evaluate_for_candidate(
                candidate_id, limit=limit, filters=filters
            )
        except UnknownCandidateError:
            raise ApiError(404, f"candidat inconnu : {candidate_id}")
        except ValueError as exc:
            # Seuils incohérents / limit invalide remontés par le service : erreur client.
            raise ApiError(400, str(exc))

        items = [self._serialize_item(candidate_id, e) for e in run.evaluations]
        return Response(
            200,
            {
                "run_id": run.run_id,
                "items": items,
                # ``total`` = nombre d'offres évaluées/persistées **après filtres et avant
                # pagination** (le POST ne pagine pas ; la pagination est du ressort de
                # GET /runs/{id}/recommendations, où ``total`` a la même sémantique).
                "total": len(items),
                "errors": list(run.errors),
            },
        )

    @staticmethod
    def _parse_filters(raw: object) -> dict | None:
        """Valide et normalise le bloc ``filters`` du corps POST (ou ``None`` si absent/vide).

        Strict : un type invalide ou une **clé inconnue** lève un 400, pour ne jamais laisser
        croire au client qu'un filtre a été pris en compte alors qu'il a été ignoré.
        ``skills`` suit la sémantique ALL (normalisée), ``contract_type`` la correspondance
        exacte (normalisée) ; une valeur vide équivaut à l'absence de contrainte.
        """
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ApiError(400, "filters doit être un objet")
        unknown = set(raw) - _ALLOWED_FILTER_KEYS
        if unknown:
            raise ApiError(400, f"filtre(s) inconnu(s) : {', '.join(sorted(unknown))}")

        contract_type = raw.get("contract_type")
        if contract_type is not None:
            if not isinstance(contract_type, str):
                raise ApiError(400, "contract_type doit être une chaîne")
            contract_type = normalize_contract(contract_type) or None

        skills_raw = raw.get("skills")
        if skills_raw is None:
            skills: list[str] = []
        elif isinstance(skills_raw, list) and all(isinstance(s, str) for s in skills_raw):
            skills = normalize_skills(skills_raw)
        else:
            raise ApiError(400, "skills doit être une liste de chaînes")

        if contract_type is None and not skills:
            return None  # filtres vides : équivalent à pas de filtre
        return {"contract_type": contract_type, "skills": skills}

    def _get_run(self, run_id: str) -> Response:
        run = self.orchestrator.get_run(run_id)
        if run is None:
            raise ApiError(404, f"run inconnu : {run_id}")
        return Response(200, self._serialize_run(run))

    def _get_run_recommendations(self, run_id: str, query: dict) -> Response:
        """Consultation **paginée** des recommandations persistées d'un run.

        Paramètres de query : ``page`` (≥ 1, défaut 1), ``page_size`` (1–100, défaut 20),
        ``advisory_status`` (pré-éval figée) et ``decision_status`` (état humain courant) —
        deux registres distincts, filtrables indépendamment. ``total`` reflète le nombre
        d'items **après filtres, avant pagination**.
        """
        page = self._query_int(query, "page", 1)
        if page < 1:
            raise ApiError(400, "page doit être un entier ≥ 1")
        page_size = self._query_int(query, "page_size", 20)
        if not 1 <= page_size <= 100:
            raise ApiError(400, "page_size doit être un entier entre 1 et 100")

        advisory_status = self._query_one(query, "advisory_status")
        if advisory_status is not None and advisory_status not in PRE_EVALUATION_STATUSES:
            raise ApiError(400, "advisory_status invalide")
        decision_status = self._query_one(query, "decision_status")
        if decision_status is not None and decision_status not in VALIDATION_STATUSES:
            raise ApiError(400, "decision_status invalide")

        run = self.orchestrator.get_run(run_id)
        if run is None:
            raise ApiError(404, f"run inconnu : {run_id}")
        items = self.orchestrator.get_run_recommendation_items(
            run, advisory_status=advisory_status, decision_status=decision_status
        )
        # ``total`` est mesuré **après filtres** (advisory/decision) mais **avant** la
        # découpe en page : c'est le cardinal du jeu filtré, pas de la page courante.
        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        total_pages = (total + page_size - 1) // page_size  # 0 si total == 0
        return Response(
            200,
            {
                "run_id": run_id,
                "items": [self._serialize_item(run.candidate_id, e) for e in page_items],
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        )

    @staticmethod
    def _query_one(query: dict, key: str) -> str | None:
        """Dernière valeur de ``key`` dans la query (``None`` si absente)."""
        values = query.get(key)
        return values[-1] if values else None

    @staticmethod
    def _query_int(query: dict, key: str, default: int) -> int:
        """Entier de query ``key`` (défaut si absent) ; 400 si non entier."""
        raw = HermesApi._query_one(query, key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            raise ApiError(400, f"{key} doit être un entier")

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
    def _serialize_item(candidate_id: str, evaluation: OfferEvaluation) -> dict:
        """Sérialise une recommandation persistée (snapshot riche) avec son id stable.

        Forme commune aux items du POST et de la consultation paginée. ``advisory_status``
        (pré-éval automatique figée) et ``decision_status`` (état de validation humaine) sont
        deux registres distincts, exposés séparément.
        """
        return {
            "recommendation_id": decision_id(candidate_id, evaluation.offer_id),
            "offer_id": evaluation.offer_id,
            "score": evaluation.score,
            "advisory_status": evaluation.advisory_status,
            "action": evaluation.action,
            "decision_status": evaluation.decision_status,
            "title": evaluation.title,
            "company": evaluation.company,
            "justification": evaluation.justification,
        }

    @staticmethod
    def _serialize_run(run: HermesRun) -> dict:
        """Représentation JSON d'une exécution journalisée (snapshot riche par offre)."""
        return {
            "run_id": run.run_id,
            "candidate_id": run.candidate_id,
            "executed_at": run.executed_at,
            "evaluations": [
                {
                    "offer_id": e.offer_id,
                    "score": e.score,
                    "decision_status": e.decision_status,
                    "advisory_status": e.advisory_status,
                    "action": e.action,
                    "title": e.title,
                    "company": e.company,
                    "justification": e.justification,
                }
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
