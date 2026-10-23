"""Adaptateur HTTP stdlib pour l'API Hermes (V2, OPP-093).

Fait le pont entre ``http.server`` et le dispatcher transport-agnostique
``HermesApi`` : lecture du corps JSON, appel de ``dispatch``, écriture de la réponse JSON.
Aucune logique métier ici — uniquement l'entrée/sortie HTTP.

Exécution : ``python -m api.server`` (base SQLite via ``OPPORTUNE_DB_PATH``).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from api.app import HermesApi
from app.auth import REVIEWER, LocalAuthProvider, User


def make_handler(api: HermesApi) -> type[BaseHTTPRequestHandler]:
    """Construit un handler HTTP branché sur ``api`` (le dispatcher porte la logique)."""

    class _Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method: str) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                self._write(400, {"error": "en-tête Content-Length invalide"})
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
            response = api.dispatch(method, self.path, body, headers)
            self._write(response.status, response.body)

        def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802 - nom imposé par http.server
            self._dispatch("POST")

        def do_DELETE(self) -> None:  # noqa: N802 - nom imposé par http.server
            # Sans ce point d'entrée, http.server répond 501 avant même le dispatcher
            # (qui, lui, gère DELETE /runs/{id} — cf. OPP-144).
            self._dispatch("DELETE")

        def do_PUT(self) -> None:  # noqa: N802 - nom imposé par http.server
            # Comme do_DELETE : sans ce point d'entrée, http.server répondrait 501 avant le
            # dispatcher (qui gère PUT /recommendations/{id}/letter — cf. OPP-147).
            self._dispatch("PUT")

        def _write(self, status: int, body: dict) -> None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:  # silence les logs par défaut
            pass

    return _Handler


def create_server(
    api: HermesApi, host: str = "127.0.0.1", port: int = 8000
) -> HTTPServer:
    """Crée un serveur HTTP servant ``api`` (non démarré ; appeler ``serve_forever``).

    Serveur **séquentiel** (une requête à la fois) et non concurrent : l'orchestrateur
    partage une unique connexion SQLite, ouverte avec ``check_same_thread=True`` et non
    conçue pour un accès multi-thread. Un ``ThreadingHTTPServer`` traiterait chaque requête
    dans un thread distinct et ferait échouer cette connexion — la concurrence viendra avec
    une connexion par requête, pas avant.
    """
    return HTTPServer((host, port), make_handler(api))


def assemble_api(conn, auth: "LocalAuthProvider") -> HermesApi:
    """Compose l'API **de production** : orchestrateur + actions + **identité locale**.

    ``auth`` est **obligatoire** : le point d'entrée réseau ne sert jamais l'API en mode
    ouvert (``auth=None`` est réservé aux tests/compatibilité). Fonction isolée pour être
    testable — vérifier qu'elle produit bien une API portant une identité.
    """
    from app.action_service import ActionService
    from app.action_store import ApplicationActionStore, OutboundMessageActionStore
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
    profiles = ProfileStore(conn)
    decision_store = DecisionStore(conn)
    decisions = DecisionService(decision_store)
    orchestrator = HermesOrchestrator(
        RecommendationService(profiles, offers),
        decisions,
        runs=RunStore(conn),
    )
    actions = ActionService(
        decisions, ApplicationActionStore(conn), OutboundMessageActionStore(conn)
    )
    # Consultation / édition du profil candidat (OPP-158) : même dépôt de profils que le scoring,
    # pour qu'une compétence ajoutée soit immédiatement prise en compte au prochain re-score.
    from app.profile_service import ProfileService

    profile_service = ProfileService(profiles)

    # Intake d'offre collée (OPP-145) : le LLM local analyse le texte avant persistance.
    # POST /offers exige donc Ollama joignable (cf. mémoire ollama-wsl2).
    # Timeout LLM généreux via OPPORTUNE_LLM_TIMEOUT (défaut 300s, convention partagée avec le
    # runner push) et plafond de tokens via OLLAMA_NUM_PREDICT (OPP-154) : un intake réaliste
    # (~85s) tient dans le défaut, sans l'ancien override codé en dur.
    llm_client = OllamaLLMClient(timeout=resolve_llm_timeout(os.environ))

    def offer_intake(raw_text: str, *, source: str, url: str = "") -> Offer:
        return intake_offer(raw_text, source=source, client=llm_client, store=offers, url=url)

    # Intake d'offre par URL (OPP-148) : fetch + extraction (BeautifulSoup, extra « scrape »)
    # puis la même chaîne d'intake que le texte collé — même client LLM, même dépôt d'offres.
    from app.offer_url_intake import intake_offer_from_url

    def offer_url_intake(url: str, *, source: str) -> Offer:
        return intake_offer_from_url(url, source=source, client=llm_client, store=offers)

    # Import de profil par CV PDF depuis le front (OPP-174) : décodage déjà fait au transport,
    # on extrait le texte (pypdf, extra « pdf ») puis on relance la MÊME chaîne d'intake que la
    # CLI (OPP-137) — même client LLM, même dépôt de profils. Upsert sur l'id du candidat ; les
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
    from app.adzuna_source import build_adzuna_source
    from app.collection_jobs import CollectionJobRegistry, ProgressCallback
    from app.collection_runner import run_collection
    from app.db import connect, database_path
    from app.offer_collection import CollectionReport

    job_db_path = database_path(conn)

    def collection_runner(
        *, what: str, where: str, max_offers: int, on_progress: ProgressCallback
    ) -> CollectionReport:
        filters = {k: v for k, v in (("what", what), ("where", where)) if v}
        job_conn = connect(job_db_path)
        try:
            job_offers = OfferStore(job_conn)
            try:
                source = build_adzuna_source(
                    os.environ, filters=filters or None, max_offers=max_offers
                )
            except AdzunaError as exc:
                return CollectionReport(
                    0, 0, 0, (), source_error=f"{type(exc).__name__}: {exc}"
                )
            return run_collection(
                source,
                llm_client=llm_client,
                store=job_offers,
                on_progress=on_progress,
            )
        finally:
            job_conn.close()

    collections = CollectionJobRegistry(collection_runner)

    # Lettre de motivation (OPP-147) : le MÊME client LLM sert l'analyse d'offre et la
    # rédaction (comme le runner push), et les dépôts décisions/profils/offres sont partagés
    # avec l'orchestrateur — une lettre se génère pour une reco déjà persistée.
    letters = LetterService(
        letters=LetterStore(conn),
        decisions=decision_store,
        profiles=profiles,
        offers=offers,
        redacteur=LLMRedacteur(llm_client),
    )

    return HermesApi(
        orchestrator,
        actions,
        auth,
        offer_intake=offer_intake,
        letters=letters,
        offer_url_intake=offer_url_intake,
        collections=collections,
        profiles=profile_service,
        cv_intake=cv_intake,
    )


def build_local_auth(owned_candidates) -> LocalAuthProvider:
    """Compose l'identité locale : un unique utilisateur ``reviewer`` propriétaire du périmètre.

    Mono-utilisateur, sans jeton (OPP-181) : l'identité est fabriquée au boot à partir du
    périmètre fourni (``OPPORTUNE_API_CANDIDATES`` pour l'instant ; dérivation dynamique depuis
    la base en OPP-183). Isolé de ``main`` pour être testable sans démarrer de serveur.
    """
    user = User(id="moi", role=REVIEWER, owned_candidates=frozenset(owned_candidates))
    return LocalAuthProvider(user)


def main() -> None:  # pragma: no cover - point d'entrée réseau, non testé
    import os
    from pathlib import Path

    from app.db import connect
    from api.app import Response
    from app.demo_candidate import DEMO_CANDIDATE_ID, reset_demo, seed_demo_candidate
    from api.space_router import SpaceRouter

    # Local-first (OPP-181) : aucun jeton requis. Le périmètre reste lu depuis l'env pour
    # l'instant ; OPP-183 le dérivera de la base (« toutes mes recherches »).
    owned = [c for c in os.environ.get("OPPORTUNE_API_CANDIDATES", "").split(",") if c]
    mine = assemble_api(connect(), build_local_auth(owned))

    # Espace démo (OPP-182) : une base d'exemple **séparée** (jamais mélangée au réel). On la
    # seede au **tout premier lancement seulement** (fichier absent) : ainsi un « repartir de
    # zéro » (vidage) n'est pas annulé par un redémarrage. Le seed est sans réseau ni LLM
    # (cf. ``app.demo_candidate``). L'utilisateur démo ne possède que le candidat démo.
    demo_db = os.environ.get("OPPORTUNE_DEMO_DB_PATH", "data/opportune-demo.db")
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
    demo = assemble_api(demo_conn, build_local_auth([DEMO_CANDIDATE_ID]))

    # Commandes d'espace démo (OPP-182), portées par le routeur donc toujours ciblées sur la
    # base démo : « repartir de zéro » (vider) et « restaurer l'exemple » (vitrine canonique).
    def _reset_demo() -> Response:
        reset_demo(demo_conn)
        return Response(200, {"status": "reset"})

    def _restore_demo() -> Response:
        reset_demo(demo_conn)
        seed_demo_candidate(demo_conn)
        return Response(200, {"status": "restored"})

    router = SpaceRouter(
        mine=mine,
        demo=demo,
        demo_commands={"/demo/reset": _reset_demo, "/demo/restore": _restore_demo},
    )
    server = create_server(router)
    host, port = server.server_address
    print(f"API Hermes à l'écoute sur http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
