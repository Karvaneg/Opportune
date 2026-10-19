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
    POST   /applications/{recommendation_id}/applied    (suivi : « j'ai candidaté », date optionnelle)
    DELETE /applications/{recommendation_id}/applied    (annule la candidature déclarée)
    POST /messages/{contact_id}/confirm                 (OPP-096, action sensible)
    POST /collect                                       (OPP-167, collecte réelle Adzuna → bilan)

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
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Protocol
from urllib.parse import parse_qs, unquote

if TYPE_CHECKING:
    from app.offer_collection import CollectionReport

from app.action_service import ActionNotAllowedError, ActionService, UnknownTargetError
from app.auth import AuthProvider, User
from app.cover_letter import CoverLetterError
from app.decision import VALIDATION_STATUSES, Decision, decision_id
from app.decision_service import PRE_EVALUATION_STATUSES, UnknownDecisionError
from app.letter import LetterError
from app.letter_service import (
    LetterExistsError,
    LetterService,
    UnknownLetterError,
    UnknownRecommendationError,
)
from app.llm_client import LLMError
from app.offer import Offer
from app.offer_analysis import OfferAnalysisError
from app.offer_normalization import normalize_contract, normalize_skills
from app.recommendation_service import UnknownCandidateError
from app.url_fetch import UnsupportedUrlError, UrlFetchError
from hermes.models import HermesRun, HermesRunSummary, OfferEvaluation
from hermes.orchestrator import HermesOrchestrator


class OfferIntake(Protocol):
    """Analyse + persiste une offre brute, et retourne l'``Offer`` créée (OPP-145).

    Encapsule ``intake_offer`` lié à un ``LLMClient`` et un dépôt d'offres : l'API reste
    transport-only et testable (on injecte un faux intake, sans réseau ni Ollama).
    """

    def __call__(self, raw_text: str, *, source: str, url: str = "") -> Offer: ...


class OfferUrlIntake(Protocol):
    """Récupère une offre depuis son URL (fetch + extraction + intake), et la retourne (OPP-148).

    Encapsule ``intake_offer_from_url`` lié à un ``LLMClient`` et un dépôt : l'API reste
    transport-only et testable (on injecte un faux intake par URL, sans réseau ni Ollama).
    """

    def __call__(self, url: str, *, source: str) -> Offer: ...


class OfferCollector(Protocol):
    """Lance une passe de collecte sur une source réelle et retourne son bilan (OPP-167).

    Encapsule l'assemblage de la source (Adzuna) + ``run_collection`` liés à un ``LLMClient``
    et à un dépôt d'offres : l'API reste transport-only et testable (on injecte un collector
    factice, sans réseau ni Ollama). Un échec de la source (identifiants, quota, panne) est
    rendu **dans le bilan** (``source_error``), pas levé — l'API répond alors 200 avec le détail.
    """

    def __call__(self, *, what: str, where: str, max_offers: int) -> "CollectionReport": ...


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
_STATS = re.compile(r"^/candidates/(?P<candidate_id>[^/]+)/stats$")
_ACTIVITY = re.compile(r"^/candidates/(?P<candidate_id>[^/]+)/activity$")
_RESCORE = re.compile(
    r"^/candidates/(?P<candidate_id>[^/]+)/offers/(?P<offer_id>[^/]+)/rescore$"
)
_RUN_RECOMMENDATIONS = re.compile(r"^/runs/(?P<run_id>[^/]+)/recommendations$")
_RUN = re.compile(r"^/runs/(?P<run_id>[^/]+)$")
_RECOMMENDATION_DECISION = re.compile(r"^/recommendations/(?P<rid>[^/]+)/decision$")
_RECOMMENDATION_LETTER = re.compile(r"^/recommendations/(?P<rid>[^/]+)/letter$")
_RECOMMENDATION = re.compile(r"^/recommendations/(?P<rid>[^/]+)$")
_APPLICATION_CONFIRM = re.compile(r"^/applications/(?P<rid>[^/]+)/confirm$")
_APPLICATION_APPLIED = re.compile(r"^/applications/(?P<rid>[^/]+)/applied$")
_MESSAGE_CONFIRM = re.compile(r"^/messages/(?P<cid>[^/]+)/confirm$")
_OFFERS = re.compile(r"^/offers$")
_COLLECT = re.compile(r"^/collect$")

# Verbes de décision exposés par l'API → statuts de validation humaine du domaine.
_DECISION_VERBS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}

# Clés de filtre acceptées par POST /recommendations (toute autre clé → 400 explicite).
_ALLOWED_FILTER_KEYS = {"contract_type", "skills"}

# POST /collect (OPP-167) : plafond d'offres par passe. La collecte est **synchrone** et paie
# un passage LLM par offre neuve ; le serveur HTTP est **séquentiel** (cf. ``create_server``),
# donc une passe longue gèle TOUTES les autres requêtes et risque le timeout client. On plafonne
# donc bas, calibré sur le temps de réponse acceptable d'un passage LLM local par offre :
# ``_COLLECT_MAX_DEFAULT`` quand le client n'en précise aucun ; ``_COLLECT_MAX_CAP`` écrête
# toute demande supérieure (le front ne peut pas forcer une passe qui timeouterait). À relever
# le jour où la collecte devient asynchrone (job en tâche de fond + sondage du bilan).
# Calibrage : ~40 s/offre neuve mesuré en live (Ollama ministral-3:3b) → défaut 5 (~3-4 min pire
# cas) / cap 10 (~6-7 min) pour rester sous un timeout proxy/navigateur raisonnable.
_COLLECT_MAX_DEFAULT = 5
_COLLECT_MAX_CAP = 10

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
        letters: LetterService | None = None,
        offer_url_intake: OfferUrlIntake | None = None,
        collector: OfferCollector | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        # Service des actions sensibles (candidature/message). Optionnel : si absent, les
        # routes /applications|/messages ne sont pas montées (404), l'API reste utilisable
        # pour la recommandation et les décisions.
        self.actions = actions
        # Intake d'offre collée (OPP-145). Optionnel : si absent (pas de LLM câblé), la route
        # POST /offers n'est pas montée (404). Injecté en prod, faux en test.
        self.offer_intake = offer_intake
        # Intake d'offre par URL (OPP-148) : fetch + extraction + intake. Optionnel ; si absent,
        # POST /offers avec un champ ``url`` seul répond 501 (le collage de texte reste possible).
        self.offer_url_intake = offer_url_intake
        # Lettre de motivation (OPP-147). Optionnel : si absent (pas de LLM câblé), les routes
        # /recommendations/{id}/letter ne sont pas montées (404). Injecté en prod, faux en test.
        self.letters = letters
        # Collecte d'offres réelles (OPP-167). Optionnel : si absent (pas de source câblée),
        # POST /collect n'est pas monté (404 neutre). Injecté en prod (Adzuna), faux en test.
        self.collector = collector
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

        match = _STATS.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_stats(unquote(match["candidate_id"]), user)

        match = _ACTIVITY.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_activity(unquote(match["candidate_id"]), user)

        match = _RESCORE.match(path)
        if match:
            self._require(method, "POST", path)
            return self._post_rescore(
                unquote(match["candidate_id"]), unquote(match["offer_id"]), user
            )

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

        match = _RECOMMENDATION_LETTER.match(path)
        if match:
            # Montée uniquement si un service de lettre est câblé (sinon 404, comme /offers POST).
            if self.letters is None:
                raise self._not_found(user, "lettre non disponible")
            rid = unquote(match["rid"])
            if method == "GET":
                return self._get_letter(rid, user)
            if method == "POST":
                return self._post_letter(rid, body, user)
            if method == "PUT":
                return self._put_letter(rid, body, user)
            if method == "DELETE":
                return self._delete_letter(rid, user)
            raise ApiError(405, f"méthode {method} non autorisée sur {path}")

        match = _RECOMMENDATION.match(path)
        if match:
            self._require(method, "GET", path)
            return self._get_recommendation(unquote(match["rid"]), user)

        if _OFFERS.match(path):
            # GET : catalogue des offres (toujours disponible, lecture du pool partagé).
            if method == "GET":
                return self._get_offers(query, user)
            # POST : intake par texte collé (OPP-145) ou par URL (OPP-148) ; la disponibilité
            # de chaque voie est vérifiée dans le handler selon le champ fourni.
            if method == "POST":
                return self._post_offers(body, user)
            raise ApiError(405, f"méthode {method} non autorisée sur {path}")

        if _COLLECT.match(path):
            # Montée uniquement si un collector est câblé (sinon 404 neutre, comme /offers POST).
            if self.collector is None:
                raise self._not_found(user, "collecte d'offres non disponible")
            self._require(method, "POST", path)
            return self._post_collect(body, user)

        # Actions sensibles : montées uniquement si le service est configuré (sinon 404).
        if self.actions is not None:
            match = _APPLICATION_CONFIRM.match(path)
            if match:
                self._require(method, "POST", path)
                return self._post_application_confirm(unquote(match["rid"]), body, user)

            match = _APPLICATION_APPLIED.match(path)
            if match:
                rid = unquote(match["rid"])
                if method == "POST":
                    return self._post_application_applied(rid, body, user)
                if method == "DELETE":
                    return self._delete_application_applied(rid, user)
                raise ApiError(405, f"méthode {method} non autorisée sur {path}")

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
                candidate_id, limit=limit, filters=filters, only_new=True
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

    def _get_stats(self, candidate_id: str, user: User | None) -> Response:
        """Agrégats de décision du candidat pour le cockpit (OPP-163).

        Owner-gated (``_guard_owner`` : 404 hors périmètre, cohérent avec l'anti-énumération
        OPP-106 ; le GET sans jeton est déjà rejeté 401 en amont). ``postule`` provient du
        service d'actions quand il est câblé, sinon 0 (candidatures non suivies dans ce mode).
        """
        self._guard_owner(user, candidate_id)
        applied_ids = (
            self.actions.applied_recommendation_ids(candidate_id)
            if self.actions is not None
            else set()
        )
        try:
            stats = self.orchestrator.candidate_stats(
                candidate_id, applied_recommendation_ids=applied_ids
            )
        except UnknownCandidateError:
            raise self._not_found(user, f"candidat inconnu : {candidate_id}")
        return Response(
            200,
            {
                "a_etudier": stats.a_etudier,
                "a_postuler": stats.a_postuler,
                "postule": stats.postule,
                "offres_total": stats.offres_total,
            },
        )

    def _get_activity(self, candidate_id: str, user: User | None) -> Response:
        """Flux d'activité récente du candidat pour le cockpit (OPP-165).

        Owner-gated comme ``/stats`` (404 neutre hors périmètre ; 401 sans jeton en amont). Les
        horodatages de lettre / candidature sont résolus **en lot** via les services câblés
        (``letters`` / ``actions``) et passés à l'orchestrateur en résolveurs, qui agrège le journal
        transversal. Le lot évite un accès par recommandation (N+1).
        """
        self._guard_owner(user, candidate_id)
        letters_at = (
            (lambda rids: self.letters.updated_at_for(rids)) if self.letters is not None else None
        )
        applied_at = (
            (lambda rids: self.actions.applied_at_for(rids)) if self.actions is not None else None
        )
        try:
            events = self.orchestrator.candidate_activity(
                candidate_id, letters_at=letters_at, applied_at=applied_at
            )
        except UnknownCandidateError:
            raise self._not_found(user, f"candidat inconnu : {candidate_id}")
        return Response(200, {"items": [self._serialize_activity_event(e) for e in events]})

    @staticmethod
    def _serialize_activity_event(event) -> dict:
        """Événement d'activité : type, horodatage, libellé FR et cible cliquable (OPP-165)."""
        return {
            "type": event.type,
            "at": event.at,
            "label": event.label,
            "target_kind": event.target_kind,
            "target_id": event.target_id,
        }

    def _post_rescore(
        self, candidate_id: str, offer_id: str, user: User | None
    ) -> Response:
        """Re-score ciblé d'une offre (OPP-150) : met à jour sa décision, renvoie l'état live.

        Propriété vérifiée sur le ``candidate_id`` du path (comme lancer un run) ; pas de
        rôle reviewer requis. 404 si le candidat est hors périmètre/inconnu **ou** si l'offre
        est introuvable/non évaluable (même message générique, anti-énumération). Une décision
        déjà arbitrée par un humain est préservée par l'orchestrateur (le front ne propose le
        bouton que sur une offre ``pending``).
        """
        self._guard_owner(user, candidate_id)
        try:
            decision = self.orchestrator.rescore_offer(candidate_id, offer_id)
        except UnknownCandidateError:
            raise self._not_found(user, f"candidat inconnu : {candidate_id}")
        if decision is None:
            raise self._not_found(user, f"offre inconnue ou non évaluable : {offer_id}")
        return Response(200, self._serialize_decision(decision))

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
        page, page_size = self._paginate(query)

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

    def _get_offers(self, query: dict, user: User | None) -> Response:
        """Catalogue **paginé** des offres (plus récentes d'abord, OPP-146).

        Le pool d'offres est **partagé** (aucun propriétaire) : lire le catalogue n'exige
        qu'un jeton valide (401 géré en amont), pas de rôle reviewer — lequel n'est requis que
        pour *curer* le pool (POST /offers). ``?candidate_id`` (optionnel) annote chaque offre
        de son **score de match** pour ce candidat ; il est alors **owner-gated** (404 neutre
        si hors périmètre, comme ailleurs), de sorte qu'on ne note jamais pour un candidat
        d'autrui. Conventions de pagination identiques à ``GET /runs``.
        """
        page, page_size = self._paginate(query)

        candidate_id = self._query_one(query, "candidate_id")
        if candidate_id is not None:
            self._guard_owner(user, candidate_id)
        # Filtre par étape d'entonnoir (OPP-164), appliqué **côté serveur** sur tout le pool
        # avant pagination : le total renvoyé concorde avec les compteurs du cockpit et la
        # pagination reste correcte même au-delà d'une page. Pertinent seulement avec un candidat.
        stage = self._query_one(query, "stage")

        # Candidatures déclarées du candidat : distinguent « postulé » d'« à postuler » dans
        # l'entonnoir (connaissance portée par ``ActionService``). Source unique côté orchestrateur.
        applied_ids = (
            self.actions.applied_recommendation_ids(candidate_id)
            if self.actions is not None and candidate_id is not None
            else set()
        )

        try:
            entries, total, funnel = self.orchestrator.list_offer_catalog(
                limit=page_size,
                offset=(page - 1) * page_size,
                candidate_id=candidate_id,
                stage=stage,
                applied_recommendation_ids=applied_ids,
            )
        except UnknownCandidateError:
            # candidat possédé mais sans profil → même 404 neutre que « hors périmètre ».
            raise self._not_found(user, f"candidat inconnu : {candidate_id}")

        total_pages = (total + page_size - 1) // page_size
        return Response(
            200,
            {
                "items": [
                    self._serialize_catalog_entry(e, *funnel.get(e.offer.id, (None, False)))
                    for e in entries
                ],
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        )

    @staticmethod
    def _serialize_catalog_entry(entry, decision_status: str | None, applied: bool) -> dict:
        """Ligne de catalogue : résumé de l'offre, son score/bande de reco, et son état d'entonnoir.

        ``decision_status`` (``None`` si pas encore décidée ou aucun candidat ciblé) et
        ``applied`` portent l'avancement **du candidat** (OPP-164) — c'est lui, et non le score
        de l'algo, qui pilote les cartes du cockpit et le filtre par étape.
        """
        offer = entry.offer
        return {
            "id": offer.id,
            "title": offer.title,
            "company": offer.company,
            "location": offer.location,
            "contract_type": offer.contract_type,
            "seniority": offer.seniority,
            "source": offer.source,
            "url": offer.url,
            "created_at": offer.created_at,
            # Type d'offre (OPP-166) : le front affiche un badge « Formation » et masque le
            # score (``None`` pour une formation) plutôt qu'un 0 ou un tiret ambigu.
            "kind": offer.kind,
            "score": entry.score,
            "action": entry.action,
            # Avancement du candidat (OPP-164) : décision humaine + candidature déclarée.
            "decision_status": decision_status,
            "applied": applied,
        }

    def _get_run(self, run_id: str, user: User | None) -> Response:
        run = self.orchestrator.get_run(run_id)
        if run is None:
            raise self._not_found(user, f"run inconnu : {run_id}")
        # Propriété résolue depuis le run persisté (jamais depuis un id du corps).
        self._guard_owner(user, run.candidate_id)
        return Response(200, self._serialize_run(run))

    def _post_offers(self, body: dict, user: User | None) -> Response:
        """Ajoute une offre, par **texte collé** (OPP-145) ou par **URL** (OPP-148).

        Curation du **pool partagé** d'offres : réservée au rôle ``reviewer`` (pas de
        propriétaire à résoudre — l'offre n'est pas liée à un candidat). Fournir **soit**
        ``text`` (le texte de l'offre), **soit** ``url`` (le back récupère la page et en
        extrait le texte) — ``text`` prime si les deux sont fournis. ``source`` est optionnel
        (défaut « collée » pour le texte, le domaine pour une URL). Les erreurs d'analyse LLM
        remontent en 502 (distinctes d'une faute de saisie, 400) ; côté URL, une cible interne
        ou un schéma invalide est un 400, un échec de récupération (injoignable, bloqué, vide)
        un 502. L'id de l'offre dérive du texte (OPP-134) → ni recoller ni refetcher ne duplique.
        """
        self._guard_reviewer(user)
        text = body.get("text")
        if isinstance(text, str) and text.strip() != "":
            return self._post_offer_text(body, text, user)

        url = body.get("url")
        if isinstance(url, str) and url.strip() != "":
            return self._post_offer_url(body, url.strip(), user)

        raise ApiError(400, "text ou url est requis (le texte de l'offre, ou son URL)")

    def _post_offer_text(self, body: dict, text: str, user: User | None) -> Response:
        """Voie texte collé (OPP-145). ``url`` facultatif, purement informatif ici."""
        if self.offer_intake is None:
            # Voie non câblée : 404 neutre (comme une route non montée), cohérent avec /letter.
            raise self._not_found(user, "intake d'offre par texte non disponible")
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

    def _post_offer_url(self, body: dict, url: str, user: User | None) -> Response:
        """Voie URL (OPP-148) : fetch + extraction + intake.

        ``UnsupportedUrlError`` (schéma non http(s), cible interne/SSRF) → 400 (faute de
        saisie) ; tout autre échec de récupération (``UrlUnreachableError``, ``BlockedError``,
        ``EmptyContentError``) → 502 (la page n'a pu être exploitée). Erreurs d'analyse LLM :
        502 comme la voie texte. Source par défaut = domaine de l'URL (utile au catalogue).
        """
        if self.offer_url_intake is None:
            # Voie non câblée : 404 neutre (comme une route non montée), cohérent avec /letter.
            raise self._not_found(user, "intake d'offre par URL non disponible")
        source = body.get("source")
        if not (isinstance(source, str) and source.strip()):
            from urllib.parse import urlsplit

            source = urlsplit(url).hostname or "url"
        else:
            source = source.strip()
        try:
            offer = self.offer_url_intake(url, source=source)
        except UnsupportedUrlError as exc:
            raise ApiError(400, f"URL refusée : {exc}")
        except UrlFetchError as exc:
            # UrlUnreachableError / BlockedError / EmptyContentError : récupération échouée.
            raise ApiError(502, f"récupération de l'offre impossible : {exc}")
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
            "created_at": offer.created_at,
            "kind": offer.kind,  # emploi | formation (OPP-166)
        }

    def _post_collect(self, body: dict, user: User | None) -> Response:
        """Déclenche une passe de collecte réelle (Adzuna) et renvoie son bilan (OPP-167).

        Curation du **pool partagé** d'offres, comme POST /offers : réservée au rôle
        ``reviewer`` (401 sans jeton géré en amont, 403 si le rôle manque). ``what`` /
        ``where`` ciblent la recherche (optionnels) ; ``max`` plafonne la passe (défaut
        ``_COLLECT_MAX_DEFAULT``, écrêté à ``_COLLECT_MAX_CAP`` car la collecte est synchrone).
        Un échec de la source est porté par le bilan (``source_error``), pas par le statut HTTP :
        la réponse reste 200 et le front affiche le détail.
        """
        self._guard_reviewer(user)
        what = self._collect_param(body, "what")
        where = self._collect_param(body, "where")
        max_offers = self._collect_max(body)
        report = self.collector(what=what, where=where, max_offers=max_offers)
        return Response(200, self._serialize_report(report))

    @staticmethod
    def _collect_param(body: dict, key: str) -> str:
        """Lit un critère texte optionnel de la collecte (``what``/``where``) ; 400 si non-chaîne."""
        raw = body.get(key, "")
        if raw is None:
            return ""
        if not isinstance(raw, str):
            raise ApiError(400, f"{key} doit être une chaîne")
        return raw.strip()

    @staticmethod
    def _collect_max(body: dict) -> int:
        """Plafond d'offres de la passe : entier ≥ 1 (défaut), écrêté au cap synchrone.

        Rejette ``bool`` (``True`` est un ``int`` en Python) et toute valeur < 1 — on ne lance
        jamais une passe au plafond ambigu. Une demande supérieure au cap est **silencieusement
        écrêtée** plutôt que refusée : le front n'a pas à connaître la borne exacte.
        """
        raw = body.get("max", _COLLECT_MAX_DEFAULT)
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
            raise ApiError(400, "max doit être un entier ≥ 1")
        return min(raw, _COLLECT_MAX_CAP)

    @staticmethod
    def _serialize_report(report: "CollectionReport") -> dict:
        """Bilan de collecte exposé au front (OPP-167) : compteurs + éventuelle erreur source.

        ``failures`` est réduit à son **cardinal** (le détail par offre reste côté serveur) ;
        ``source_error`` est ``None`` en cas de passe saine, sinon le message rendant visible
        une panne de la source (identifiants manquants, quota, réseau)."""
        return {
            "collected": report.collected,
            "stored": report.stored,
            "duplicates": report.duplicates,
            "failures": len(report.failures),
            "source_error": report.source_error,
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
        page, page_size = self._paginate(query)

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

    @staticmethod
    def _paginate(query: dict) -> tuple[int, int]:
        """Lit et valide les paramètres de pagination communs à tous les listings.

        ``page`` (≥ 1, défaut 1) et ``page_size`` (1–100, défaut 20) ; 400 si hors bornes.
        Source unique de la convention (``GET /runs``, ``/offers``, recommandations d'un run)
        pour ne pas dupliquer bornes et messages. Retourne ``(page, page_size)``.
        """
        page = HermesApi._query_int(query, "page", 1)
        if page < 1:
            raise ApiError(400, "page doit être un entier ≥ 1")
        page_size = HermesApi._query_int(query, "page_size", 20)
        if not 1 <= page_size <= 100:
            raise ApiError(400, "page_size doit être un entier entre 1 et 100")
        return page, page_size

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

    # --- Lettre de motivation (OPP-147) : GET / POST / PUT / DELETE -----------------

    def _guard_letter_target(self, user: User | None, recommendation_id: str) -> None:
        """Gardes communes aux routes lettre : existence (reco) → propriété → rôle ``reviewer``.

        La lettre est une ressource sensible rattachée à une recommandation persistée : on
        résout son propriétaire depuis la décision (jamais depuis le corps), 404 neutre si la
        reco est absente/hors périmètre (anti-énumération), 403 si le rôle manque. Toutes les
        opérations lettre (y compris la lecture) exigent ``reviewer`` — c'est du contenu de
        candidature, pas une donnée de catalogue partagée.
        """
        decision = self.orchestrator.get_recommendation(recommendation_id)
        if decision is None:
            raise self._not_found(user, f"recommandation inconnue : {recommendation_id}")
        self._guard_owner(user, decision.candidate_id)
        self._guard_reviewer(user)

    def _get_letter(self, recommendation_id: str, user: User | None) -> Response:
        """Renvoie la lettre de la reco, ou 404 neutre si aucune n'est encore générée."""
        self._guard_letter_target(user, recommendation_id)
        letter = self.letters.get(recommendation_id)
        if letter is None:
            raise self._not_found(user, "aucune lettre pour cette recommandation")
        return Response(200, self._serialize_letter(letter))

    def _post_letter(
        self, recommendation_id: str, body: dict, user: User | None
    ) -> Response:
        """Génère (LLM) la lettre d'une reco ; ``source=ai``.

        Idempotent côté humain : si une lettre existe déjà, renvoie **409** plutôt que
        d'écraser en silence — le front présente alors le choix et renvoie
        ``{"regenerate": true}`` pour un remplacement conscient (même d'une lettre éditée).
        201 à la première création, 200 sur régénération. Les erreurs LLM / génération
        inexploitable remontent en 502 (comme l'intake d'offre), distinctes d'une faute de
        saisie (400) ou d'un conflit d'état (409).
        """
        self._guard_letter_target(user, recommendation_id)
        regenerate = body.get("regenerate", False)
        if not isinstance(regenerate, bool):
            raise ApiError(400, "regenerate doit valoir true ou false (booléen)")
        try:
            letter, created = self.letters.generate(recommendation_id, overwrite=regenerate)
        except LetterExistsError as exc:
            raise ApiError(409, str(exc))
        except UnknownRecommendationError:
            # Reco résolue par la garde mais offre/profil disparu : 404 neutre.
            raise self._not_found(user, f"recommandation inconnue : {recommendation_id}")
        except CoverLetterError as exc:
            raise ApiError(502, f"génération de lettre inexploitable : {exc}")
        except LLMError as exc:
            raise ApiError(502, f"service de génération indisponible : {exc}")
        return Response(201 if created else 200, self._serialize_letter(letter))

    def _put_letter(
        self, recommendation_id: str, body: dict, user: User | None
    ) -> Response:
        """Édite (remplace) le corps de la lettre ; ``source=human``.

        Édite une lettre **existante** (404 neutre sinon : la création passe par POST).
        ``body`` requis et non vide (400 sinon).
        """
        self._guard_letter_target(user, recommendation_id)
        new_body = body.get("body")
        if not isinstance(new_body, str) or new_body.strip() == "":
            raise ApiError(400, "body est requis (le corps de la lettre)")
        try:
            letter = self.letters.edit(recommendation_id, new_body)
        except UnknownLetterError:
            raise self._not_found(user, "aucune lettre à éditer pour cette recommandation")
        except LetterError as exc:
            raise ApiError(400, str(exc))
        return Response(200, self._serialize_letter(letter))

    def _delete_letter(self, recommendation_id: str, user: User | None) -> Response:
        """Supprime la lettre de la reco ; 404 neutre si aucune n'existait (idempotence douce)."""
        self._guard_letter_target(user, recommendation_id)
        if not self.letters.delete(recommendation_id):
            raise self._not_found(user, "aucune lettre à supprimer pour cette recommandation")
        return Response(200, {"deleted": recommendation_id})

    @staticmethod
    def _serialize_letter(letter) -> dict:
        """Représentation JSON d'une lettre persistée (champs exploités par le front)."""
        return {
            "recommendation_id": letter.recommendation_id,
            "body": letter.body,
            "source": letter.source,
            "model": letter.model,
            "created_at": letter.created_at,
            "updated_at": letter.updated_at,
        }

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

    def _post_application_applied(
        self, recommendation_id: str, body: dict, user: User | None
    ) -> Response:
        """Déclare qu'on a **réellement candidaté** à une recommandation (suivi, OPP-xxx).

        Pointage déclaratif, pas un envoi : **aucune** garde ``{"confirm": true}`` (contrairement
        à l'intention), mais les mêmes gardes d'accès (existence → propriété → rôle ``reviewer``).
        ``applied_at`` (optionnel) permet de dater une candidature **passée** ; absent = aujourd'hui.
        Exige une intention préalablement notée (sinon 409). Idempotent. Renvoie l'état courant.
        """
        self._guard_sensitive_target(user, recommendation_id)
        applied_at = self._parse_applied_at(body)
        try:
            self.actions.mark_applied(recommendation_id, applied_at)
        except ActionNotAllowedError as exc:
            raise ApiError(409, str(exc))
        return Response(200, self._serialize_application(recommendation_id) or {})

    def _delete_application_applied(
        self, recommendation_id: str, user: User | None
    ) -> Response:
        """Annule une candidature déclarée par erreur : retour à l'état « intention notée ».

        Mêmes gardes d'accès que la déclaration. Exige une intention existante (sinon 409).
        Idempotent. Renvoie l'état courant (``applied`` repasse à ``false``).
        """
        self._guard_sensitive_target(user, recommendation_id)
        try:
            self.actions.unmark_applied(recommendation_id)
        except ActionNotAllowedError as exc:
            raise ApiError(409, str(exc))
        return Response(200, self._serialize_application(recommendation_id) or {})

    @staticmethod
    def _parse_applied_at(body: dict) -> str | None:
        """Valide la date de candidature optionnelle du corps (``applied_at``).

        ``None``/absent → la couche métier datera à aujourd'hui. Sinon, exige une chaîne ISO
        8601 parseable (date seule ``YYYY-MM-DD`` ou datetime) — 400 autrement. On rejette aussi
        une date clairement **future** : candidater « demain » n'a pas de sens pour un pointage
        de suivi (la même borne existe côté UI via ``max``, on la double ici pour les appels
        directs à l'API). Une tolérance d'un jour absorbe les décalages de fuseau du client.
        """
        raw = body.get("applied_at")
        if raw is None:
            return None
        if not isinstance(raw, str):
            raise ApiError(400, "applied_at doit être une date ISO 8601 (chaîne)")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            raise ApiError(400, "applied_at doit être une date ISO 8601 valide")
        if parsed.date() > datetime.now(timezone.utc).date() + timedelta(days=1):
            raise ApiError(400, "applied_at ne peut pas être dans le futur")
        return raw

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
            # Type d'offre (OPP-166) : permet au front de badger « Formation » une fiche
            # historique (décision posée avant la distinction). ``None`` si l'offre a disparu.
            "kind": offer.kind if offer is not None else None,
            # Provenance + date d'ingestion de l'offre (OPP-112) : lien vers l'annonce d'origine
            # et « ajoutée le… » sur la fiche. ``None``/vide si l'offre a disparu.
            "url": offer.url if offer is not None else None,
            "created_at": offer.created_at if offer is not None else None,
            "justification": decision.justification,
            "status": decision.status,
            "comment": decision.comment,
            "history": [
                {"status": ev.status, "at": ev.at, "comment": ev.comment}
                for ev in decision.history
            ],
            # Intention de candidater notée (OPP-096). ``None`` si aucune, ou si le service
            # d'actions n'est pas câblé — le front n'affiche alors aucun marqueur.
            "application": self._serialize_application(decision.id),
        }

    def _serialize_application(self, recommendation_id: str) -> dict | None:
        """État persistant de l'intention de candidater, pour affichage (OPP-096).

        ``None`` si le service d'actions n'est pas câblé ou si aucune intention n'a été notée.
        ``status`` (``simulated`` en V2) est exposé tel quel : le front en fait un libellé
        lisible plutôt que de montrer le jargon.
        """
        if self.actions is None:
            return None
        application = self.actions.get_application(recommendation_id)
        if application is None:
            return None
        return {
            "confirmed": True,
            "confirmed_at": application.confirmed_at,
            "status": application.status,
            # Cycle de vie : ``applied`` = l'humain a déclaré avoir candidaté (OPP-xxx).
            "applied": application.applied_at is not None,
            "applied_at": application.applied_at,
        }
