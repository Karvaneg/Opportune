"""Adaptateur HTTP stdlib pour l'API Hermes (V2, OPP-093).

Fait le pont entre ``http.server`` et le dispatcher transport-agnostique
``HermesApi`` : lecture du corps JSON, appel de ``dispatch``, écriture de la réponse JSON.
Aucune logique métier ici — uniquement l'entrée/sortie HTTP.

Exécution : ``python -m api.server`` (base SQLite via ``OPPORTUNE_DB_PATH``).
"""

from __future__ import annotations

import functools
import json
import sqlite3
import sys
import traceback
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Mapping

from api.app import HermesApi
from api.frontend_assets import content_type_for, resolve_static_file
from api.host_guard import allowed_hosts, is_host_allowed
from api.origin_guard import EXTRA_ORIGINS_ENV, allowed_origins, is_write_allowed
from app.auth import LocalAuthProvider, User

# Préfixe des appels de données (cf. front : ``src/api/client.ts``). En mode packagé,
# l'API sert aussi le front : on route ``/api/*`` vers le dispatcher et le reste vers les
# assets statiques. Le front envoie toujours ce préfixe ; on le retire avant dispatch, car
# les routes du dispatcher sont à la racine (``/offers``, pas ``/api/offers``).
_API_PREFIX = "/api"
# Taille max d'un corps de requête : l'import d'un export (200 Mo max) encodé en base64 (+33 %)
# dans du JSON, avec une marge. Au-delà, 413 sans lire le corps.
MAX_REQUEST_BYTES = 280 * 1024 * 1024


def _is_api_path(path: str) -> bool:
    """Le chemin relève-t-il des **données** (préfixe ``/api``) plutôt que du front ?

    Source unique de la frontière ``/api`` : tous les verbes s'y appuient pour router (données
    vers le dispatcher, reste vers le front), de sorte que lecture et écriture tracent la **même**
    ligne. La query string est ignorée (``/api/offers?x=1`` relève bien des données).
    """
    head = path.split("?", 1)[0]
    return head == _API_PREFIX or head.startswith(_API_PREFIX + "/")


def _strip_api_prefix(path: str) -> str:
    """Retire le préfixe ``/api`` du chemin avant dispatch.

    ``/api/offers`` → ``/offers`` ; ``/api`` → ``/`` ; ``/api?x=1`` → ``/?x=1`` (query préservée).
    Un chemin hors ``/api`` (appel au dispatcher direct, tests) est rendu tel quel — le préfixe est
    une convention du front, pas du dispatcher.
    """
    if not _is_api_path(path):
        return path
    rest = path[len(_API_PREFIX):]
    # ``_is_api_path`` garantit que ``rest`` vaut ``""``, ``?...`` (``/api`` nu + query) ou ``/...``.
    # On préfixe un ``/`` dans les deux premiers cas pour ne jamais perdre la query string.
    return rest if rest.startswith("/") else "/" + rest


def make_handler(
    api: HermesApi,
    static_dir: Path | None = None,
    *,
    allow_dev_front: bool = False,
    extra_origins: tuple[str, ...] = (),
) -> type[BaseHTTPRequestHandler]:
    """Construit un handler HTTP branché sur ``api`` (le dispatcher porte la logique).

    ``static_dir`` (OPP-191) : répertoire du front compilé à servir pour les requêtes GET
    hors ``/api``. ``None`` → aucun service statique (mode dev, où Vite sert le front) : une
    telle requête répond 404.

    ``allow_dev_front`` / ``extra_origins`` (OPP-233) : origines acceptées en plus de celle de
    l'API pour les écritures (cf. ``origin_guard``). Faux par défaut : seul ``main`` l'active,
    hors app packagée.
    """

    @functools.cache
    def guard_sets(api_port: int) -> tuple[frozenset[str], frozenset[str]]:
        """(origines, hôtes) autorisés pour ``api_port``. Calculés une fois : le port est fixe
        pour la vie du serveur, mais n'est connu qu'une fois lié (``port=0`` en test)."""
        origins = allowed_origins(
            api_port, allow_dev_front=allow_dev_front, extra=extra_origins
        )
        return origins, allowed_hosts(api_port)

    # Cache mémoire des assets du front (OPP-194) : ``{chemin résolu: (signature, etag, octets)}``.
    # Le ``dist`` ne change pas pendant la vie du process ; sans cache, chaque GET relisait tout le
    # fichier du disque. La signature (mtime + taille) détecte malgré tout une recompilation en dev
    # et recharge. Capturé par la closure, partagé par toutes les requêtes (serveur séquentiel).
    static_cache: dict[Path, tuple[tuple[int, int], str, bytes]] = {}

    def cached_asset(target: Path) -> tuple[str, bytes]:
        """Renvoie ``(etag, octets)`` pour ``target``, en relisant le disque seulement si besoin."""
        stat = target.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = static_cache.get(target)
        if cached is not None and cached[0] == signature:
            return cached[1], cached[2]
        payload = target.read_bytes()
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        static_cache[target] = (signature, etag, payload)
        return etag, payload

    class _Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method: str) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self._write(400, {"error": "en-tête Content-Length invalide"})
                return
            if length > MAX_REQUEST_BYTES:
                # Refusé **avant** lecture : un corps démesuré ne doit pas occuper la mémoire ni
                # bloquer l'unique thread du serveur pendant qu'on le lit.
                self.close_connection = True
                self._write(413, {"error": "requête trop volumineuse"})
                return
            raw = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                self._write(400, {"error": "corps JSON invalide"})
                return
            if not isinstance(body, dict):
                self._write(400, {"error": "le corps doit être un objet JSON"})
                return
            # Les en-têtes portent l'authentification (Authorization: Bearer …) ; on les
            # transmet au dispatcher (clé insensible à la casse, gérée en aval).
            headers = {key: value for key, value in self.headers.items()}
            # Filet transport (OPP-207) : une exception du dispatcher ne doit JAMAIS remonter à
            # http.server, qui fermerait la connexion sans réponse (« empty reply » opaque côté
            # client). On rend toujours une réponse JSON — en journalisant la traceback serveur.
            try:
                response = api.dispatch(method, _strip_api_prefix(self.path), body, headers)
            except sqlite3.OperationalError as exc:
                # Verrou SQLite (p. ex. écriture concurrente d'une collecte de fond) : erreur
                # **transitoire**, pas un plantage → 503, pour que le client invite à réessayer.
                if "locked" in str(exc).lower():
                    self._write(
                        503,
                        {"error": "Service occupé (opération concurrente en cours). "
                                  "Réessaie dans un instant."},
                    )
                else:
                    traceback.print_exc()
                    self._write(500, {"error": "Erreur interne du serveur."})
            except Exception:
                traceback.print_exc()
                self._write(500, {"error": "Erreur interne du serveur."})
            else:
                self._write(response.status, response.body)

        def _host_refused(self) -> bool:
            """Refuse (403) une requête dont ``Host`` n'est pas un nom local (OPP-233).

            Bloque le DNS rebinding, en lecture comme en écriture. Rend vrai si refusée.
            """
            _, hosts = guard_sets(self.server.server_address[1])
            if is_host_allowed(self.headers.get("Host"), hosts):
                return False
            self.close_connection = True
            self._write(403, {"error": "hôte non autorisé"})
            return True

        def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
            if self._host_refused():
                return
            # ``/api/*`` = données (dispatcher) ; tout le reste = front statique (OPP-191).
            if _is_api_path(self.path):
                self._dispatch("GET")
            else:
                self._serve_static()

        def do_POST(self) -> None:  # noqa: N802 - nom imposé par http.server
            self._dispatch_api("POST")

        def do_DELETE(self) -> None:  # noqa: N802 - nom imposé par http.server
            # Sans ce point d'entrée, http.server répond 501 avant même le dispatcher
            # (qui, lui, gère DELETE /runs/{id} — cf. OPP-144).
            self._dispatch_api("DELETE")

        def do_PUT(self) -> None:  # noqa: N802 - nom imposé par http.server
            # Comme do_DELETE : sans ce point d'entrée, http.server répondrait 501 avant le
            # dispatcher (qui gère PUT /recommendations/{id}/letter — cf. OPP-147).
            self._dispatch_api("PUT")

        def _dispatch_api(self, method: str) -> None:
            """Dispatche une écriture, mais seulement sous ``/api`` : même frontière que ``do_GET``.

            Un verbe d'écriture hors ``/api`` ne correspond à aucune donnée (le reste relève du
            front, qui n'accepte pas d'écriture) → 404 franc, symétrique du GET qui y sert le front.
            Une écriture dont l'en-tête ``Origin`` n'est pas celle de l'app → 403 (OPP-233).
            """
            if self._host_refused():
                return
            if not _is_api_path(self.path):
                self._write(404, {"error": "route inconnue"})
                return
            # OPP-233 : une écriture envoyée par la page d'un autre site est refusée **avant**
            # lecture du corps et dispatch, donc sans aucun effet.
            origin = self.headers.get("Origin")
            origins, _ = guard_sets(self.server.server_address[1])
            if not is_write_allowed(origin, origins):
                # Message explicite : un front de dev ouvert depuis une autre adresse (IP WSL,
                # ``--host``) tombe ici, et doit savoir comment s'autoriser.
                print(
                    f"Écriture refusée : origine {origin!r} non autorisée "
                    f"(à ajouter dans {EXTRA_ORIGINS_ENV} si c'est ton front).",
                    file=sys.stderr,
                )
                self.close_connection = True
                self._write(
                    403,
                    {"error": f"origine non autorisée : {origin}. Si c'est le front "
                              f"d'Opportune, ajoute cette origine à {EXTRA_ORIGINS_ENV}."},
                )
                return
            self._dispatch(method)

        def _serve_static(self) -> None:
            """Sert un fichier du front compilé (OPP-191), avec fallback SPA sur index.html.

            Sans ``static_dir`` (dev : Vite sert le front), toute requête non-``/api`` est un
            404 JSON. La résolution du fichier (anti-traversée, SPA) est déléguée à
            ``resolve_static_file`` ; ici on ne fait que l'entrée/sortie HTTP.
            """
            if static_dir is None:
                self._write(404, {"error": "route inconnue"})
                return
            # Même filet transport que ``_dispatch`` (OPP-207) : la résolution de chemin ou la
            # lecture disque peuvent lever (URL malformée avec octet nul → ``ValueError`` dans
            # ``resolve``, fichier retiré en pleine requête → ``OSError``). Sans ce garde,
            # l'exception remonterait à http.server qui fermerait la connexion sans réponse.
            try:
                target = resolve_static_file(static_dir, self.path)
                if target is None:
                    self._write(404, {"error": "route inconnue"})
                    return
                etag, payload = cached_asset(target)
            except ValueError:
                self._write(400, {"error": "chemin invalide"})
                return
            except Exception:
                traceback.print_exc()
                self._write(500, {"error": "Erreur interne du serveur."})
                return
            # Revalidation par ETag : le navigateur garde l'asset en cache et ne reçoit que le
            # statut 304 (sans corps) tant que le fichier n'a pas changé — évite de renvoyer le
            # bundle à chaque rechargement.
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.end_headers()
                return
            self._write_bytes(
                200, payload, content_type_for(target.name), extra_headers={"ETag": etag}
            )

        def _write(self, status: int, body: dict) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self._write_bytes(status, payload, "application/json; charset=utf-8")

        def _write_bytes(
            self,
            status: int,
            payload: bytes,
            content_type: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:  # silence les logs par défaut
            pass

    return _Handler


# Port d'écoute par défaut de l'API (+ front en mode packagé). Surchargeable par
# ``OPPORTUNE_API_PORT`` : la coquille Tauri lit la **même** variable pour savoir où joindre le
# sidecar (cf. ``src-tauri/src/main.rs``), de sorte qu'un port occupé se règle à un seul endroit.
DEFAULT_API_PORT = 8000


def resolve_api_port(env: Mapping[str, str]) -> int:
    """Port d'écoute de l'API depuis ``OPPORTUNE_API_PORT`` ; :data:`DEFAULT_API_PORT` sinon.

    Tolérant comme les autres réglages de confort (cf. ``app.llm._env_int``) : absent, vide, non
    entier ou hors de la plage valide des ports → défaut, plutôt qu'un refus de démarrer sur une
    valeur mal saisie.
    """
    raw = env.get("OPPORTUNE_API_PORT")
    if raw is None or raw.strip() == "":
        return DEFAULT_API_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_API_PORT
    return port if 1 <= port <= 65535 else DEFAULT_API_PORT


def create_server(
    api: HermesApi,
    host: str = "127.0.0.1",
    port: int = DEFAULT_API_PORT,
    static_dir: Path | None = None,
    *,
    allow_dev_front: bool = False,
    extra_origins: tuple[str, ...] = (),
) -> HTTPServer:
    """Crée un serveur HTTP servant ``api`` (non démarré ; appeler ``serve_forever``).

    Serveur **séquentiel** (une requête à la fois) et non concurrent : l'orchestrateur
    partage une unique connexion SQLite, ouverte avec ``check_same_thread=True`` et non
    conçue pour un accès multi-thread. Un ``ThreadingHTTPServer`` traiterait chaque requête
    dans un thread distinct et ferait échouer cette connexion — la concurrence viendra avec
    une connexion par requête, pas avant.

    ``static_dir`` (OPP-191) : front compilé à servir pour les requêtes hors ``/api``.
    ``allow_dev_front`` / ``extra_origins`` (OPP-233) : cf. :func:`make_handler`.
    """
    handler = make_handler(
        api, static_dir, allow_dev_front=allow_dev_front, extra_origins=extra_origins
    )
    return HTTPServer((host, port), handler)


def assemble_api(
    conn, auth: "LocalAuthProvider", searches=None, settings_dir: "Path | None" = None
) -> HermesApi:
    """Compose l'API **de production** : orchestrateur + actions + **identité locale**.

    ``auth`` est **obligatoire** : le point d'entrée réseau ne sert jamais l'API en mode
    ouvert (``auth=None`` est réservé aux tests/compatibilité). Fonction isolée pour être
    testable — vérifier qu'elle produit bien une API portant une identité.

    ``searches`` (OPP-184) est le **registre du périmètre** de cet espace : le même que celui
    dont ``auth`` dérive le périmètre, pour que le CRUD « recherche » (/searches) et l'auth
    partagent une seule source de vérité. Optionnel pour rester compatible avec les appelants
    existants ; ``main`` le fournit toujours.

    ``settings_dir`` est le dossier des **réglages** (clés Adzuna, flux RSS, entreprises
    ciblées) de cet espace. Par défaut le dossier de données de l'app (espace réel) ; la démo
    reçoit un sous-dossier dédié pour que ses réglages soient **isolés** du réel (ni partage, ni
    fuite d'un espace à l'autre).
    """
    from app.action_service import ActionService
    from app.action_store import ApplicationActionStore, OutboundMessageActionStore
    from app.application_tracking_service import ApplicationTrackingService
    from app.application_tracking_store import ApplicationTrackingStore
    from app.candidate_offer_store import CandidateOfferStore
    import os

    from app.decision_service import DecisionService
    from app.decision_store import DecisionStore
    from app.letter_service import LetterService
    from app.letter_store import LetterStore
    from app.llm import resolve_llm_timeout
    from app.llm_client import OllamaLLMClient
    from app.offer import Offer
    from app.offer_intake_service import intake_offer
    from app.offer_store import OfferStore
    from app.profile_store import ProfileStore
    from app.recommendation_service import RecommendationService
    from app.redacteur import LLMRedacteur
    from hermes.orchestrator import HermesOrchestrator
    from hermes.run_store import RunStore

    if auth is None:
        raise ValueError("assemble_api exige un LocalAuthProvider (pas de mode ouvert en prod)")

    # Un seul dépôt d'offres partagé entre le scoring (RecommendationService) et l'intake
    # collé (POST /offers) : une offre fraîchement ajoutée est immédiatement évaluable.
    offers = OfferStore(conn)
    # Une base créée avant OPP-243 garde la table Discord ``submissions`` : on la retire au boot.
    from app.database_schema import drop_obsolete_tables

    drop_obsolete_tables(conn)
    # Offres propres à chaque recherche (OPP-186) : la table de liens est créée après ``offers``
    # (et après le registre des recherches) pour que sa migration rattache l'existant.
    memberships = CandidateOfferStore(conn)
    profiles = ProfileStore(conn)
    decision_store = DecisionStore(conn)
    decisions = DecisionService(decision_store)
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers, memberships),
        decisions,
        runs=RunStore(conn),
    )
    application_store = ApplicationActionStore(conn)
    actions = ActionService(
        decisions, application_store, OutboundMessageActionStore(conn)
    )
    # Suivi post-candidature (OPP-223) : partage le dépôt des candidatures (pour la garde
    # « déclarée candidatée » et le candidate_id) et persiste ses événements à part.
    tracking = ApplicationTrackingService(
        application_store, ApplicationTrackingStore(conn)
    )
    # Consultation / édition du profil candidat (OPP-158) : même dépôt de profils que le scoring,
    # pour qu'une compétence ajoutée soit immédiatement prise en compte au prochain re-score.
    from app.profile_service import ProfileService

    profile_service = ProfileService(profiles)

    # Intake d'offre collée (OPP-145) : le LLM local analyse le texte avant persistance.
    # POST /offers exige donc Ollama joignable (cf. mémoire ollama-wsl2).
    # Timeout LLM généreux via OPPORTUNE_LLM_TIMEOUT (défaut 300s) et plafond de tokens via
    # OLLAMA_NUM_PREDICT (OPP-154) : un intake réaliste (~85s) tient dans le défaut, sans
    # l'ancien override codé en dur.
    llm_client = OllamaLLMClient(timeout=resolve_llm_timeout(os.environ))

    def offer_intake(raw_text: str, *, source: str, candidate_id: str, url: str = "") -> Offer:
        offer = intake_offer(raw_text, source=source, client=llm_client, store=offers, url=url)
        memberships.link(candidate_id, offer.id)
        return offer

    # Intake d'offre par URL (OPP-148) : fetch + extraction (BeautifulSoup, extra « scrape »)
    # puis la même chaîne d'intake que le texte collé — même client LLM, même dépôt d'offres.
    from app.offer_url_intake import intake_offer_from_url

    def offer_url_intake(url: str, *, source: str, candidate_id: str) -> Offer:
        offer = intake_offer_from_url(url, source=source, client=llm_client, store=offers)
        memberships.link(candidate_id, offer.id)
        return offer

    # Import de profil par CV PDF depuis le front (OPP-174) : décodage déjà fait au transport,
    # on extrait le texte (pypdf, extra « pdf ») puis on lance la chaîne d'intake (OPP-137) avec
    # le client LLM et le dépôt de profils de l'espace. Upsert sur l'id du candidat ; les
    # faits verrouillés à la main (OPP-138) sont préservés par ``intake_profile``.
    from app.profile_intake_service import intake_profile
    from hermes.pdf_extract import extract_text_from_pdf_bytes

    def cv_intake(candidate_id: str, pdf_bytes: bytes, *, contract_type, **preferences):
        text = extract_text_from_pdf_bytes(pdf_bytes)
        return intake_profile(
            text,
            contract_type=contract_type,
            client=llm_client,
            store=profiles,
            id=candidate_id,
            **preferences,
        )

    # Collecte d'offres réelles **asynchrone** (OPP-170) : un registre lance la passe Adzuna dans
    # un thread de fond et la suit par sondage. Le runner ouvre sa **propre** connexion SQLite —
    # il tourne hors du thread HTTP, et la connexion partagée (``check_same_thread``) ne peut pas
    # servir deux threads ; WAL + ``busy_timeout`` (cf. ``app.db``) autorisent l'écriture du job à
    # coexister avec les lectures de l'API. Cette connexion vise la **même base** que ``conn``
    # (chemin dérivé de la connexion injectée, pas le défaut d'``OPPORTUNE_DB_PATH``) : sinon un
    # ``conn`` sur un autre fichier ferait écrire le job dans une base distincte et les offres
    # collectées n'apparaîtraient jamais au catalogue. Les erreurs de la source (identifiants
    # Adzuna manquants, quota, panne) restent rendues **dans le bilan** (``source_error``).
    from app.adzuna_client import AdzunaError
    from app.adzuna_credentials_store import (
        AdzunaCredentialsStore,
        default_credentials_path,
        resolve_adzuna_credentials,
    )
    from importlib.util import find_spec

    from app.adzuna_source import build_adzuna_source
    from app.collection_jobs import CollectionJobRegistry, ProgressCallback
    from app.db import connect, database_path
    from app.offer_collection import CollectionReport, collect_offers, source_cap
    from app.rss_feeds_store import RssFeedsStore, default_rss_feeds_path
    from app.rss_source import build_rss_source
    from app.ats_companies_store import AtsCompaniesStore, default_ats_companies_path
    from app.ats_source import AtsSource, build_ats_source

    job_db_path = database_path(conn)
    # Identifiants Adzuna saisis par l'utilisateur (OPP-222), rangés dans le dossier de données de
    # l'app (secret, hors dépôt). Le même fichier sert les deux espaces (clés propres à la machine).
    adzuna_credentials = AdzunaCredentialsStore(default_credentials_path(settings_dir))
    # URLs de flux RSS saisies par l'utilisateur (OPP-195) : faute de flux FR gratuit par défaut,
    # la source RSS n'est alimentée que par ces URLs (non secrètes, relues telles quelles dans l'UI).
    rss_feeds = RssFeedsStore(default_rss_feeds_path(settings_dir))
    # Entreprises ciblées sur un ATS (OPP-226) : pages carrière saisies par l'utilisateur, une
    # liste par espace (non secrète, relue telle quelle dans l'UI).
    ats_companies = AtsCompaniesStore(default_ats_companies_path(settings_dir))
    # Délais de relance (OPP-235) : un fichier par espace, délais par défaut s'il est absent.
    from app.follow_up_settings_store import FollowUpSettingsStore, default_follow_up_path

    follow_up_settings = FollowUpSettingsStore(default_follow_up_path(settings_dir))

    def collection_runner(
        *,
        source: str,
        what: str,
        where: str,
        max_offers: int,
        on_progress: ProgressCallback,
        should_cancel: Callable[[], bool],
        candidate_id: str,
    ) -> CollectionReport:
        job_conn = connect(job_db_path)
        # Renseignée seulement pour la source « entreprises ciblées » (bilan enrichi après la passe).
        ats_source: AtsSource | None = None
        try:
            job_offers = OfferStore(job_conn)
            job_memberships = CandidateOfferStore(job_conn)
            try:
                if source == "rss":
                    # Flux saisis par l'utilisateur ; ``what``/``where`` ne s'appliquent pas ici.
                    feeds = rss_feeds.load()
                    if not feeds:
                        return CollectionReport(
                            0, 0, 0, (),
                            source_error="Aucun flux RSS configuré : ajoutez des URLs de flux dans les Réglages.",
                        )
                    # Le nettoyage HTML du contenu RSS exige l'extra ``scrape`` (BeautifulSoup) :
                    # sans lui, chaque offre échouerait. On échoue vite et clair.
                    if find_spec("bs4") is None:
                        return CollectionReport(
                            0, 0, 0, (),
                            source_error="Collecte RSS indisponible : le composant de nettoyage HTML n'est pas installé.",
                        )
                    collection_source = build_rss_source(feeds, max_offers=source_cap(max_offers))
                elif source == "ats":
                    # Entreprises ciblées (OPP-226) : ``what`` filtre les intitulés (facultatif),
                    # ``where`` est ignoré (la source ne garde que la France, RG-11/RG-12).
                    companies = ats_companies.load()
                    if not companies:
                        return CollectionReport(
                            0, 0, 0, (),
                            source_error=(
                                "Aucune entreprise ciblée : ajoute des pages carrière "
                                "dans les Réglages."
                            ),
                        )
                    ats_source = build_ats_source(
                        companies, max_offers=source_cap(max_offers), title_query=what
                    )
                    collection_source = ats_source
                elif source == "adzuna":
                    filters = {k: v for k, v in (("what", what), ("where", where)) if v}
                    credentials = resolve_adzuna_credentials(adzuna_credentials)
                    collection_source = build_adzuna_source(
                        credentials, filters=filters or None, max_offers=source_cap(max_offers)
                    )
                else:
                    # La source est déjà validée en amont (``_collect_source`` : 400 sinon) ; ce
                    # garde-fou évite qu'une **nouvelle** source ajoutée à la liste sans branche
                    # ici ne retombe silencieusement sur Adzuna et collecte la mauvaise source.
                    return CollectionReport(
                        0, 0, 0, (), source_error=f"Source de collecte inconnue : {source}."
                    )
            except AdzunaError as exc:
                return CollectionReport(
                    0, 0, 0, (), source_error=f"{type(exc).__name__}: {exc}"
                )
            report = collect_offers(
                collection_source,
                client=llm_client,
                store=job_offers,
                on_progress=on_progress,
                should_cancel=should_cancel,
                # ``max`` compte les offres **neuves** : les doublons ne consomment pas le
                # plafond (les sources sont plafonnées plus large, cf. ``source_cap``).
                max_new=max_offers,
                candidate_id=candidate_id,
                memberships=job_memberships,
            )
            if ats_source is None:
                return report
            # Le socle ignore les filtres France/poste et les échecs par entreprise : la source
            # les a comptés, on les reporte dans le bilan (RG-11, RG-12, RG-20).
            return replace(
                report,
                excluded=ats_source.excluded,
                off_target=ats_source.off_target,
                warnings=tuple(ats_source.warnings),
            )
        finally:
            job_conn.close()

    collections = CollectionJobRegistry(collection_runner)

    # Lettre de motivation (OPP-147) : le MÊME client LLM sert l'analyse d'offre et la
    # rédaction, et les dépôts décisions/profils/offres sont partagés
    # avec l'orchestrateur — une lettre se génère pour une reco déjà persistée.
    letters = LetterService(
        letters=LetterStore(conn),
        decisions=decision_store,
        profiles=profiles,
        offers=offers,
        redacteur=LLMRedacteur(llm_client),
    )

    # Mise en route du LLM local au 1er lancement (OPP-193) : statut Ollama/modèle/RAM et
    # téléchargement du modèle suivi par sondage. Même hôte/modèle que le client de génération
    # (OLLAMA_HOST / OLLAMA_MODEL, cf. app.llm) pour viser exactement le LLM que le métier utilise.
    from app.llm import DEFAULT_MODEL, DEFAULT_OLLAMA_HOST
    from app.llm_setup_service import LLMSetupService

    # On note les modèles qu'Opportune télécharge elle-même (OPP-251), avec le dossier où ils
    # atterrissent, pour ne jamais supprimer plus tard un modèle que la personne avait déjà.
    from app.model_download_recorder import make_download_recorder
    from app.model_origin import MODEL_ORIGIN_FILENAME, ModelOriginStore
    from app.paths import user_data_dir

    model_origin = ModelOriginStore(user_data_dir() / MODEL_ORIGIN_FILENAME)
    llm_setup = LLMSetupService(
        model=DEFAULT_MODEL,
        host=DEFAULT_OLLAMA_HOST,
        on_downloaded=make_download_recorder(model_origin, host=DEFAULT_OLLAMA_HOST),
    )

    # Désinstallation depuis l'app (OPP-252) : même modèle, même hôte et même fichier d'origine
    # que la mise en route, pour décrire exactement ce qu'Opportune a installé.
    from app.uninstall_service import UninstallService

    uninstall = UninstallService(
        data_dir=user_data_dir(),
        origin=model_origin,
        model=DEFAULT_MODEL,
        host=DEFAULT_OLLAMA_HOST,
    )

    return HermesApi(
        orchestrator,
        actions,
        auth,
        tracking=tracking,
        offer_intake=offer_intake,
        letters=letters,
        offer_url_intake=offer_url_intake,
        collections=collections,
        profiles=profile_service,
        cv_intake=cv_intake,
        searches=searches,
        llm_setup=llm_setup,
        uninstall=uninstall,
        adzuna_credentials=adzuna_credentials,
        rss_feeds=rss_feeds,
        follow_up_settings=follow_up_settings,
        ats_companies=ats_companies,
        conn=conn,
    )


def build_local_auth(owned_provider) -> LocalAuthProvider:
    """Compose l'identité locale : un unique utilisateur au périmètre **dynamique**.

    Mono-utilisateur, sans jeton (OPP-181). Périmètre dérivé de la base (OPP-183) :
    ``owned_provider`` est un callable rappelé **à chaque requête** qui rend les ids du
    périmètre courant (registre des candidats), et non un ``frozenset`` figé au boot. Isolé
    de ``main`` pour être testable sans démarrer de serveur.
    """
    user = User(id="moi", owned_candidates=frozenset())
    return LocalAuthProvider(user, owned_provider=owned_provider)


def _data_transfer_for(api, conn, *, settings_dir: "Path | None"):
    """Service d'export / import (OPP-232) d'un espace : sa base et ses fichiers de réglages.

    ``settings_dir`` ``None`` = dossier de réglages par défaut (« Mon espace »). L'import est
    refusé pendant une collecte de l'espace (elle écrit dans la base).
    """
    from app import __version__
    from app.adzuna_credentials_store import default_credentials_path
    from app.ats_companies_store import default_ats_companies_path
    from app.data_transfer_service import DataTransferService
    from app.database_schema import ensure_schema
    from app.follow_up_settings_store import default_follow_up_path
    from app.rss_feeds_store import default_rss_feeds_path

    return DataTransferService(
        conn=conn,
        settings_files=[
            default_credentials_path(settings_dir),
            default_rss_feeds_path(settings_dir),
            default_ats_companies_path(settings_dir),
            default_follow_up_path(settings_dir),
        ],
        app_version=__version__,
        ensure_schema=ensure_schema,
        is_busy=lambda: api.collections is not None and api.collections.active_job() is not None,
    )


def main() -> None:  # pragma: no cover - point d'entrée réseau, non testé
    import os
    from pathlib import Path

    from app.db import connect
    from api.app import Response
    from app.candidate_registry import CandidateRegistry
    from app.demo_candidate import migrate_demo_search_label, reset_demo, seed_demo_candidate
    from app.demo_settings import (
        ensure_demo_settings_seeded,
        mark_demo_settings_seeded,
        seed_demo_settings,
    )
    from app.profile_store import ProfileStore
    from api.space_router import SpaceRouter

    # Périmètre dynamique en base (OPP-183/184) : « Mon espace » dérive ses candidats du registre,
    # recalculé à chaque requête. À chaque boot on **réunit** (insert-or-ignore, idempotent) les
    # profils déjà présents, pour qu'une install antérieure au registre retrouve ses recherches
    # sans intervention. L'enrôlement courant passe par la **création à chaud** (``POST /searches``,
    # OPP-184) — l'ancien bootstrap par ``OPPORTUNE_API_CANDIDATES`` a été retiré (OPP-188).
    mine_conn = connect()
    mine_registry = CandidateRegistry(mine_conn)
    mine_registry.ensure(ProfileStore(mine_conn).list_ids())
    mine = assemble_api(
        mine_conn, build_local_auth(mine_registry.list_ids), searches=mine_registry
    )
    # Export / import des données (OPP-232), pour chaque espace sur sa propre base et ses propres
    # réglages : « Mon espace » ici, la Démo plus bas (import après un « repartir de zéro »).
    mine.data_transfer = _data_transfer_for(mine, mine_conn, settings_dir=None)

    # Espace démo (OPP-182) : une base d'exemple **séparée** (jamais mélangée au réel). On la
    # seede au **tout premier lancement seulement** (fichier absent) : ainsi un « repartir de
    # zéro » (vidage) n'est pas annulé par un redémarrage. Le seed est sans réseau ni LLM
    # (cf. ``app.demo_candidate``). L'utilisateur démo ne possède que le candidat démo.
    from app.paths import user_data_dir

    demo_db = os.environ.get("OPPORTUNE_DEMO_DB_PATH") or str(
        user_data_dir() / "opportune-demo.db"
    )
    demo_is_new = demo_db == ":memory:" or not Path(demo_db).exists()
    demo_conn = connect(demo_db)
    if demo_is_new:
        # Si ce **premier** seed échoue, le fichier à peine créé resterait « existant mais vide »
        # et ne serait plus jamais re-seedé (traité comme un vidage volontaire). On le retire donc
        # pour que le prochain démarrage réessaie — sans toucher à une base démo déjà en place.
        try:
            seed_demo_candidate(demo_conn)
        except Exception:
            demo_conn.close()
            if demo_db != ":memory:":
                Path(demo_db).unlink(missing_ok=True)
            raise
    else:
        # Base démo déjà en place : son libellé date peut-être d'avant OPP-245 (« Alex Démo »).
        migrate_demo_search_label(demo_conn)
    # Périmètre démo : son candidat vitrine est posé par le **seed** (premier lancement et
    # « Restaurer l'exemple »). On ne force **plus** le slot au boot (OPP-195) : après un
    # « repartir de zéro », le périmètre doit rester vide, y compris au redémarrage — le
    # sélecteur invite alors à créer une nouvelle recherche, plutôt que de ressusciter la démo.
    demo_registry = CandidateRegistry(demo_conn)
    # Réglages de la démo **isolés** dans un sous-dossier dédié (OPP-195) : les clés Adzuna et les
    # flux RSS saisis dans « Mon espace » ne doivent ni être partagés, ni fuiter vers la démo.
    demo_settings_dir = user_data_dir() / "demo"
    demo = assemble_api(
        demo_conn,
        build_local_auth(demo_registry.list_ids),
        searches=demo_registry,
        settings_dir=demo_settings_dir,
    )
    demo.data_transfer = _data_transfer_for(demo, demo_conn, settings_dir=demo_settings_dir)
    # Réglages de collecte pré-remplis (OPP-226), pour essayer RSS et ATS sans rien saisir :
    # posés une fois (témoin dans le dossier des réglages démo, indépendant de la base), puis à
    # « Restaurer l'exemple ». Un échec d'écriture ne bloque pas le démarrage : sans témoin posé,
    # le prochain démarrage réessaie.
    try:
        ensure_demo_settings_seeded(
            demo_settings_dir, rss_feeds=demo.rss_feeds, ats_companies=demo.ats_companies
        )
    except OSError as exc:
        print(f"Réglages démo non pré-remplis (nouvel essai au prochain démarrage) : {exc}",
              file=sys.stderr)

    def _seed_demo_settings() -> None:
        seed_demo_settings(rss_feeds=demo.rss_feeds, ats_companies=demo.ats_companies)
        mark_demo_settings_seeded(demo_settings_dir)

    # Commandes d'espace démo (OPP-182), portées par le routeur donc toujours ciblées sur la
    # base démo : « repartir de zéro » (vider) et « restaurer l'exemple » (vitrine canonique).
    # Le vidage emporte aussi les **réglages** de la démo (OPP-195) : repartir de zéro ne doit
    # rien conserver, clés Adzuna, flux RSS et entreprises ciblées compris.
    def _clear_demo_settings() -> None:
        demo.adzuna_credentials.clear()
        demo.rss_feeds.clear()
        demo.ats_companies.clear()
        demo.follow_up_settings.clear()
        # Le témoin reste (ou est posé) : un redémarrage ne doit pas re-remplir après un vidage.
        mark_demo_settings_seeded(demo_settings_dir)

    def _reset_demo() -> Response:
        reset_demo(demo_conn)
        _clear_demo_settings()
        return Response(200, {"status": "reset"})

    def _restore_demo() -> Response:
        reset_demo(demo_conn)
        _clear_demo_settings()
        seed_demo_candidate(demo_conn)
        _seed_demo_settings()
        return Response(200, {"status": "restored"})

    router = SpaceRouter(
        mine=mine,
        demo=demo,
        demo_commands={"/demo/reset": _reset_demo, "/demo/restore": _restore_demo},
    )
    # Front compilé servi par l'API en mode packagé (OPP-191) : un seul binaire = app
    # complète. En dev (dist absent), ``static_dir`` est ``None`` et c'est Vite qui sert.
    from api.frontend_assets import frontend_dist_dir

    static_dir = frontend_dist_dir()
    from api.origin_guard import parse_extra_origins
    from app.paths import is_frozen

    # OPP-233 : les origines du front de dev (Vite) ne sont acceptées que hors app packagée.
    # Critère ``is_frozen`` et pas ``static_dir`` : en dev, un ``frontend/dist`` construit
    # n'empêche pas de travailler avec ``npm run dev``.
    server = create_server(
        router,
        port=resolve_api_port(os.environ),
        static_dir=static_dir,
        allow_dev_front=not is_frozen(),
        extra_origins=parse_extra_origins(os.environ),
    )
    host, port = server.server_address
    if static_dir is not None:
        print(f"Opportune à l'écoute sur http://{host}:{port} (front + API)")
    else:
        print(f"API Hermes à l'écoute sur http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
