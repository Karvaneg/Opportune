"""Dispatcher de l'API Hermes (V2, OPP-093).

``HermesApi.dispatch(method, path, body)`` route une requête vers l'orchestrateur et rend
une ``Response`` (statut + corps JSON-sérialisable), **sans dépendre du transport HTTP**.
C'est là que vit le routage ; ``server.py`` n'en est que l'adaptateur socket.

Endpoints :

    GET  /me                                           (OPP-103, sonde d'auth + identité)
    GET  /runs                                          (OPP-101, listing paginé, périmètre)
    POST /candidates/{candidate_id}/recommendations   (OPP-093, filtres OPP-095)
    GET  /runs/{run_id}                                (OPP-094)
    GET  /runs/{run_id}/recommendations                (OPP-095, paginé + filtres)
    GET  /recommendations/{recommendation_id}          (OPP-094)
    POST /recommendations/{recommendation_id}/decision (OPP-094)
    POST /applications/{recommendation_id}/confirm      (OPP-096, action sensible)
    POST /messages/{contact_id}/confirm                 (OPP-096, action sensible)

Le POST recommande et pré-évalue les offres du candidat (filtrables via ``filters`` :
``contract_type`` exact, ``skills`` en ALL), journalise l'exécution (``run_id``, snapshot
riche par offre) et crée des décisions ``pending`` — mais **ne déclenche aucune candidature
ni message**. Il renvoie les items du run (``total`` = nb d'offres évaluées après filtres) ;
la consultation détaillée se fait paginée via ``GET /runs/{run_id}/recommendations``.

``advisory_status`` (``approved`` / ``pending`` / ``rejected``) est la **pré-évaluation
automatique** figée ; ``decision_status`` est l'**état de validation humaine courant**
(relu en direct). Les endpoints de décision **enregistrent une décision humaine**
(approve/reject/defer), persistée et historisée.

Les endpoints ``/confirm`` (OPP-096) déclenchent des **actions sensibles** (candidature,
message) sous **confirmation explicite obligatoire** (``{"confirm": true}``) : un statut
``approved`` seul ne suffit **jamais**. La candidature exige en plus une décision humaine
``approved`` (sinon 409) ; ils sont idempotents (``already_confirmed``) et **simulés** à ce
stade. Ces routes ne sont montées que si un ``ActionService`` est fourni à ``HermesApi``.

Sécurité (OPP-097) : si un ``AuthProvider`` est fourni, **toute** route métier exige un jeton
``Authorization: Bearer`` valide (401 sinon), puis un contrôle de **propriété** (l'utilisateur
n'accède qu'à ses candidats/runs — sinon **404**, on ne révèle pas l'existence d'une ressource
d'autrui) et, pour la validation humaine et les actions sensibles, le **rôle ``reviewer``**
(sinon **403**). Le propriétaire est toujours résolu depuis la **ressource persistée**, jamais
d'un identifiant du corps. Sans ``AuthProvider`` (``auth=None``), l'API reste **ouverte** :
mode de **compatibilité/test uniquement**, à ne pas utiliser en production.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, unquote

from app.action_service import ActionNotAllowedError, ActionService, UnknownTargetError
from app.auth import AuthProvider, User
from app.decision import VALIDATION_STATUSES, Decision, decision_id
from app.decision_service import PRE_EVALUATION_STATUSES, UnknownDecisionError
from app.llm_client import LLMError
from app.offer import Offer
from app.offer_analysis import OfferAnalysisError
from app.offer_normalization import normalize_contract, normalize_skills
from app.recommendation_service import UnknownCandidateError
from hermes.models import HermesRun, HermesRunSummary, OfferEvaluation
from hermes.orchestrator import HermesOrchestrator


class OfferIntake(Protocol):
    """Analyse + persiste une offre brute, et retourne l'``Offer`` créée (OPP-145).

    Encapsule ``intake_offer`` lié à un ``LLMClient`` et un dépôt d'offres : l'API reste
    transport-only et testable (on injecte un faux intake, sans réseau ni Ollama).
    """

    def __call__(self, raw_text: str, *, source: str, url: str = "") -> Offer: ...


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
_ME = re.compile(r"^/me$")
_RUNS = re.compile(r"^/runs$")
_RECOMMENDATIONS = re.compile(r"^/candidates/(?P<candidate_id>[^/]+)/recommendations$")
_RUN_RECOMMENDATIONS = re.compile(r"^/runs/(?P<run_id>[^/]+)/recommendations$")
_RUN = re.compile(r"^/runs/(?P<run_id>[^/]+)$")
_RECOMMENDATION_DECISION = re.compile(r"^/recommendations/(?P<rid>[^/]+)/decision$")
_RECOMMENDATION = re.compile(r"^/recommendations/(?P<rid>[^/]+)$")
_APPLICATION_CONFIRM = re.compile(r"^/applications/(?P<rid>[^/]+)/confirm$")
_MESSAGE_CONFIRM = re.compile(r"^/messages/(?P<cid>[^/]+)/confirm$")
_OFFERS = re.compile(r"^/offers$")

# Verbes de décision exposés par l'API → statuts de validation humaine du domaine.
_DECISION_VERBS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}

# Clés de filtre acceptées par POST /recommendations (toute autre clé → 400 explicite).
_ALLOWED_FILTER_KEYS = {"contract_type", "skills"}

# Corps 404 générique en mode authentifié : « absent » et « hors périmètre » doivent être
# indistinguables pour ne pas révéler l'existence d'une ressource d'autrui (anti-énumération).
_NOT_FOUND = "ressource introuvable"


class HermesApi:
    """Adapte l'orchestrateur Hermes en une API requête → réponse, sans transport."""

    def __init__(
        self,
        orchestrator: HermesOrchestrator,
        actions: ActionService | None = None,
        auth: AuthProvider | None = None,
        offer_intake: OfferIntake | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        # Service des actions sensibles (candidature/message). Optionnel : si absent, les
        # routes /applications|/messages ne sont pas montées (404), l'API reste utilisable
        # pour la recommandation et les décisions.
        self.actions = actions
        # Intake d'offre collée (OPP-145). Optionnel : si absent (pas de LLM câblé), la route
        # POST /offers n'est pas montée (404). Injecté en prod, faux en test.
        self.offer_intake = offer_intake
        # Fournisseur d'authentification. ``None`` = **mode ouvert** (compatibilité/test) :
        # aucune vérification. Le serveur réel DOIT en injecter un — ne pas s'appuyer sur
        # ``None`` en production. Avec un fournisseur, toute route métier exige un jeton
        # valide (401) puis contrôle propriété/rôle (404/403).
        self.auth = auth

    def dispatch(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        headers: dict | None = None,
    ) -> Response:
        """Route ``(method, path, body, headers)`` vers un handler ; convertit toute ``ApiError``.

        Le corps est optionnel ; la query string est parsée ; les en-têtes servent à
        l'authentification (``Authorization: Bearer``) quand un fournisseur est configuré.
        """
        path_only, _, query_string = path.partition("?")
        query = parse_qs(query_string)
        try:
            user = self._authenticate(headers or {})
            return self._route(method.upper(), path_only, body or {}, query, user)
        except ApiError as exc:
            return Response(exc.status, {"error": exc.message})
        except Exception:  # noqa: BLE001 — filet de sécurité : jamais de connexion coupée
            # Toute erreur inattendue devient un 500 propre plutôt qu'une exception non
            # gérée qui remonterait jusqu'au socket (réponse absente / connexion tuée).
            return Response(500, {"error": "erreur interne"})

    def _authenticate(self, headers: dict) -> User | None:
        """Résout l'utilisateur courant : ``None`` en mode ouvert, sinon un ``User`` ou 401."""
        if self.auth is None:
            return None
        user = self.auth.authenticate(headers)
        if user is None:
            raise ApiError(401, "authentification requise")
        return user

    def _route(
        self, method: str, path: str, body: dict, query: dict, user: User | None
    ) -> Response:
        if _ME.match(path):
            self._require(method, "GET", path)
            return self._get_me(user)

        if _RUNS.match(path):
            self._require(method, "GET", path)
            return self._get_runs(query, user)

        match = _RECOMMENDATIONS.match(path)
        if match:
            self._require(method, "POST", path)
            return self._post_recommendations(unquote(match["candidate_id"]), body, user)

        match = _RUN_RECOMMENDATIONS.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_run_recommendations(unquote(match["run_id"]), query, user)

        match = _RUN.match(path)
        if match:
            run_id = unquote(match["run_id"])
            if method == "GET":
                return self._get_run(run_id, user)
            if method == "DELETE":
                return self._delete_run(run_id, user)
            raise ApiError(405, f"méthode {method} non autorisée sur {path}")

        match = _RECOMMENDATION_DECISION.match(path)
        if match:
            self._require(method, "POST", path)
            return self._post_decision(unquote(match["rid"]), body, user)

        match = _RECOMMENDATION.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_recommendation(unquote(match["rid"]), user)

        # Intake d'offre collée : monté uniquement si un LLM est câblé (sinon 404).
        if self.offer_intake is not None and _OFFERS.match(path):
            self._require(method, "POST", path)
            return self._post_offers(body, user)

        # Actions sensibles : montées uniquement si le service est configuré (sinon 404).
        if self.actions is not None:
            match = _APPLICATION_CONFIRM.match(path)
            if match:
                self._require(method, "POST", path)
                return self._post_application_confirm(unquote(match["rid"]), body, user)

            match = _MESSAGE_CONFIRM.match(path)
            if match:
                self._require(method, "POST", path)
                return self._post_message_confirm(unquote(match["cid"]), body, user)

        raise ApiError(404, f"route inconnue : {method} {path}")

    @staticmethod
    def _require(method: str, expected: str, path: str) -> None:
        if method != expected:
            raise ApiError(405, f"méthode {method} non autorisée sur {path}")

    @staticmethod
    def _get_me(user: User | None) -> Response:
        """Identité du porteur du jeton — sonde de validation d'authentification.

        Route protégée sans ressource : un jeton invalide/absent est déjà rejeté en amont
        (401) par ``_authenticate``. Elle permet à un client de vérifier qu'un jeton est
        **accepté** (et d'afficher qui il est) sans deviner d'identifiant de ressource. En
        mode ouvert (``user is None``, tests), il n'existe aucune identité applicative.
        """
        if user is None:
            return Response(
                200, {"id": None, "role": None, "owned_count": 0, "owned_candidate_ids": []}
            )
        return Response(
            200,
            {
                "id": user.id,
                "role": user.role,
                "owned_count": len(user.owned_candidates),
                # Les candidats du **propriétaire** (son propre périmètre) : permet au front
                # de lancer un run sans deviner d'identifiant (OPP-143). Trié pour un rendu
                # déterministe.
                "owned_candidate_ids": sorted(user.owned_candidates),
            },
        )

    # --- Autorisation (propriété / rôle) : résolue depuis la ressource persistée ---

    @staticmethod
    def _guard_owner(user: User | None, candidate_id: str) -> None:
        """Refuse (404) l'accès à une ressource hors du périmètre du propriétaire.

        404 (et non 403) : on ne révèle pas l'existence d'une ressource d'autrui. En mode
        ouvert (``user is None``), aucune restriction.
        """
        if user is not None and not user.owns(candidate_id):
            raise ApiError(404, _NOT_FOUND)

    @staticmethod
    def _guard_reviewer(user: User | None) -> None:
        """Exige le rôle ``reviewer`` (403) — pour une ressource que l'utilisateur possède déjà."""
        if user is not None and not user.is_reviewer:
            raise ApiError(403, "rôle reviewer requis")

    @staticmethod
    def _not_found(user: User | None, open_message: str) -> ApiError:
        """404 pour une ressource absente, **indistinguable** d'un refus de propriété.

        En mode authentifié (``user is not None``), le corps est le **même** message
        générique que ``_guard_owner`` : sans quoi un appelant distinguerait « n'existe
        pas » de « existe mais hors périmètre » et pourrait énumérer les ressources
        d'autrui. En mode ouvert, aucun enjeu d'énumération → message descriptif conservé.
        """
        return ApiError(404, _NOT_FOUND if user is not None else open_message)

    def _post_recommendations(
        self, candidate_id: str, body: dict, user: User | None
    ) -> Response:
        # Propriété vérifiée sur le ``candidate_id`` **du path** (jamais un id du corps) ;
        # pas de rôle reviewer requis pour lancer une recommandation.
        self._guard_owner(user, candidate_id)
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

    def _get_runs(self, query: dict, user: User | None) -> Response:
        """Listing **paginé** des runs du périmètre (plus récents d'abord).

        Périmètre : en mode authentifié, seuls les runs des candidats **possédés** sont
        listés (un périmètre vide → liste vide) ; on ne révèle jamais les runs d'autrui, et
        aucun 404 n'est requis — une collection filtrée ne divulgue pas l'existence de
        ressources tierces (cohérent OPP-097). En mode ouvert, tous les runs. Conventions de
        pagination identiques à ``GET /runs/{run_id}/recommendations`` ; ``total`` est le
        cardinal **avant** découpe en page.
        """
        page = self._query_int(query, "page", 1)
        if page < 1:
            raise ApiError(400, "page doit être un entier ≥ 1")
        page_size = self._query_int(query, "page_size", 20)
        if not 1 <= page_size <= 100:
            raise ApiError(400, "page_size doit être un entier entre 1 et 100")

        scope = None if user is None else user.owned_candidates
        summaries, total = self.orchestrator.list_run_summaries(
            scope, limit=page_size, offset=(page - 1) * page_size
        )
        total_pages = (total + page_size - 1) // page_size  # 0 si total == 0
        return Response(
            200,
            {
                "items": [self._serialize_run_summary(s) for s in summaries],
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        )

    def _get_run(self, run_id: str, user: User | None) -> Response:
        run = self.orchestrator.get_run(run_id)
        if run is None:
            raise self._not_found(user, f"run inconnu : {run_id}")
        # Propriété résolue depuis le run persisté (jamais depuis un id du corps).
        self._guard_owner(user, run.candidate_id)
        return Response(200, self._serialize_run(run))

    def _post_offers(self, body: dict, user: User | None) -> Response:
        """Ajoute une offre en collant son texte (OPP-145) : analyse LLM → persistance.

        Curation du **pool partagé** d'offres : réservée au rôle ``reviewer`` (pas de
        propriétaire à résoudre — l'offre n'est pas liée à un candidat). ``text`` obligatoire
        (400 si vide) ; ``source`` (défaut « collée ») et ``url`` optionnels. Les erreurs
        d'analyse LLM (réponse non exploitable, service indisponible) remontent en 502 pour
        les distinguer d'une faute de saisie (400). L'id de l'offre dérive du texte (OPP-134)
        → re-coller le même texte met à jour l'offre au lieu de la dupliquer.
        """
        self._guard_reviewer(user)
        text = body.get("text")
        if not isinstance(text, str) or text.strip() == "":
            raise ApiError(400, "text est requis (le texte de l'offre)")
        source = body.get("source")
        source = source.strip() if isinstance(source, str) and source.strip() else "collée"
        url = body.get("url", "")
        if not isinstance(url, str):
            raise ApiError(400, "url doit être une chaîne")

        try:
            offer = self.offer_intake(text, source=source, url=url)
        except ValueError as exc:
            raise ApiError(400, str(exc))
        except OfferAnalysisError as exc:
            raise ApiError(502, f"analyse de l'offre non exploitable : {exc}")
        except LLMError as exc:
            raise ApiError(502, f"service d'analyse indisponible : {exc}")
        return Response(201, self._serialize_offer(offer))

    @staticmethod
    def _serialize_offer(offer: Offer) -> dict:
        """Représentation JSON d'une offre persistée (champs exploités par le front)."""
        return {
            "id": offer.id,
            "title": offer.title,
            "company": offer.company,
            "location": offer.location,
            "skills": list(offer.skills),
            "seniority": offer.seniority,
            "contract_type": offer.contract_type,
            "summary": offer.summary,
            "source": offer.source,
            "url": offer.url,
        }

    def _delete_run(self, run_id: str, user: User | None) -> Response:
        """Supprime un run (OPP-144) : existence → propriété → rôle reviewer, puis suppression.

        Ordre des gardes identique aux actions sensibles (on ne révèle rien à un appelant non
        autorisé). Idempotent : re-supprimer un run déjà retiré renvoie 404 neutre.
        """
        run = self.orchestrator.get_run(run_id)
        if run is None:
            raise self._not_found(user, f"run inconnu : {run_id}")
        self._guard_owner(user, run.candidate_id)
        self._guard_reviewer(user)
        self.orchestrator.delete_run(run_id)
        return Response(200, {"deleted": run_id})

    def _get_run_recommendations(
        self, run_id: str, query: dict, user: User | None
    ) -> Response:
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
            raise self._not_found(user, f"run inconnu : {run_id}")
        self._guard_owner(user, run.candidate_id)
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

    def _get_recommendation(self, recommendation_id: str, user: User | None) -> Response:
        decision = self.orchestrator.get_recommendation(recommendation_id)
        if decision is None:
            raise self._not_found(user, f"recommandation inconnue : {recommendation_id}")
        # Propriété résolue depuis la décision persistée (son ``candidate_id``).
        self._guard_owner(user, decision.candidate_id)
        return Response(200, self._serialize_decision(decision))

    def _post_decision(self, recommendation_id: str, body: dict, user: User | None) -> Response:
        # Validation humaine = action réservée : existence → propriété → rôle reviewer,
        # dans cet ordre (on ne révèle une ressource d'autrui ni son état).
        if user is not None:
            decision = self.orchestrator.get_recommendation(recommendation_id)
            if decision is None:
                raise self._not_found(user, f"recommandation inconnue : {recommendation_id}")
            self._guard_owner(user, decision.candidate_id)
            self._guard_reviewer(user)
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
            raise self._not_found(user, f"recommandation inconnue : {recommendation_id}")
        return Response(200, self._serialize_decision(decision))

    def _post_application_confirm(
        self, recommendation_id: str, body: dict, user: User | None
    ) -> Response:
        """Confirme (explicitement) l'intention de candidater à une recommandation.

        Action sensible : quand l'auth est active, on vérifie **successivement** existence de
        la cible → propriété → rôle ``reviewer`` (404/404/403) **avant** la garde
        ``{"confirm": true}`` (400), pour ne rien révéler à un appelant non autorisé. Exige
        ensuite une décision humaine ``approved`` (sinon 409). Idempotent.
        """
        self._guard_sensitive_target(user, recommendation_id)
        self._require_confirm(body)
        try:
            action, already = self.actions.confirm_application(recommendation_id)
        except ActionNotAllowedError as exc:
            raise ApiError(409, str(exc))
        return Response(200, self._serialize_action(action, already))

    def _post_message_confirm(
        self, contact_id: str, body: dict, user: User | None
    ) -> Response:
        """Confirme (explicitement) l'intention d'envoyer un message à une cible.

        Mêmes gardes d'action sensible que la candidature (existence → propriété → rôle,
        puis ``{"confirm": true}``). Cible inconnue → 404. Idempotent par ``contact_id``.
        """
        self._guard_sensitive_target(user, contact_id)
        self._require_confirm(body)
        try:
            action, already = self.actions.confirm_message(contact_id)
        except UnknownTargetError:
            raise ApiError(404, f"cible inconnue : {contact_id}")
        return Response(200, self._serialize_action(action, already))

    def _guard_sensitive_target(self, user: User | None, target_id: str) -> None:
        """Gardes d'une action sensible : existence → propriété → rôle ``reviewer``.

        La cible d'une action (candidature/message) est une recommandation persistée
        (``target_id`` = son id) : on résout son propriétaire depuis la décision, jamais
        depuis le corps. En mode ouvert (``user is None``), aucune garde (l'existence/état
        est alors traité par le service, cf. OPP-096).
        """
        if user is None:
            return
        decision = self.orchestrator.get_recommendation(target_id)
        if decision is None:
            # Authentifié : même 404 que le refus de propriété (anti-énumération).
            raise self._not_found(user, "cible inconnue")
        self._guard_owner(user, decision.candidate_id)
        self._guard_reviewer(user)

    @staticmethod
    def _require_confirm(body: dict) -> None:
        """Garde anti-déclenchement : ``confirm`` doit valoir **strictement** ``true``.

        ``is True`` (et non un simple test de véracité) : un ``1``, une chaîne ``"true"`` ou
        toute autre valeur truthy est rejetée en 400 — la confirmation d'une action sensible
        doit être un booléen explicite.
        """
        if body.get("confirm") is not True:
            raise ApiError(400, "confirm doit valoir true (booléen)")

    @staticmethod
    def _serialize_action(action, already_confirmed: bool) -> dict:
        """Réponse d'une confirmation d'action (candidature ou message)."""
        return {
            "action_id": action.action_id,
            "status": action.status,
            "already_confirmed": already_confirmed,
        }

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
    def _serialize_run_summary(summary: HermesRunSummary) -> dict:
        """Sérialise le résumé d'un run pour le **listing** : identité + volumétrie, sans les
        évaluations détaillées (lourdes). Le détail se consulte via ``GET /runs/{run_id}``."""
        return {
            "run_id": summary.run_id,
            "candidate_id": summary.candidate_id,
            "executed_at": summary.executed_at,
            "evaluation_count": summary.evaluation_count,
            "error_count": summary.error_count,
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

    def _serialize_decision(self, decision: Decision) -> dict:
        """Représentation JSON d'une décision, historique inclus (recommandation d'origine préservée).

        ``title``/``company`` sont résolus depuis l'offre d'origine (``offer_id``) pour que la
        page reco dédiée soit lisible (OPP-112) ; ``None`` si l'offre a disparu — le front
        retombe alors sur l'``offer_id``.
        """
        offer = self.orchestrator.get_offer(decision.offer_id)
        return {
            "recommendation_id": decision.id,
            "candidate_id": decision.candidate_id,
            "offer_id": decision.offer_id,
            "action": decision.action,
            "score": decision.score,
            "title": offer.title if offer is not None else None,
            "company": offer.company if offer is not None else None,
            "justification": decision.justification,
            "status": decision.status,
            "comment": decision.comment,
            "history": [
                {"status": ev.status, "at": ev.at, "comment": ev.comment}
                for ev in decision.history
            ],
        }
