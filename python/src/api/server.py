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
            response = api.dispatch(method, self.path, body)
            self._write(response.status, response.body)

        def do_GET(self) -> None:  # noqa: N802 - nom imposé par http.server
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802 - nom imposé par http.server
            self._dispatch("POST")

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


def main() -> None:  # pragma: no cover - point d'entrée réseau, non testé
    from app.action_service import ActionService
    from app.action_store import ApplicationActionStore, OutboundMessageActionStore
    from app.db import connect
    from app.decision_service import DecisionService
    from app.decision_store import DecisionStore
    from app.offer_store import OfferStore
    from app.profile_store import ProfileStore
    from app.recommendation_service import RecommendationService
    from hermes.orchestrator import HermesOrchestrator
    from hermes.run_store import RunStore

    conn = connect()
    decisions = DecisionService(DecisionStore(conn))
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        decisions,
        runs=RunStore(conn),
    )
    actions = ActionService(
        decisions, ApplicationActionStore(conn), OutboundMessageActionStore(conn)
    )
    server = create_server(HermesApi(orchestrator, actions))
    host, port = server.server_address
    print(f"API Hermes à l'écoute sur http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
