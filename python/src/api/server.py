"""Adaptateur HTTP stdlib pour l'API Hermes (V2, OPP-093).

Fait le pont entre ``http.server`` et le dispatcher transport-agnostique
``HermesApi`` : lecture du corps JSON, appel de ``dispatch``, écriture de la réponse JSON.
Aucune logique métier ici — uniquement l'entrée/sortie HTTP.

Exécution : ``python -m api.server`` (base SQLite via ``OPPORTUNE_DB_PATH``).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from api.app import HermesApi
from app.auth import REVIEWER, AuthProvider, TokenRecord, User


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


def assemble_api(conn, auth: "AuthProvider") -> HermesApi:
    """Compose l'API **de production** : orchestrateur + actions + **authentification**.

    ``auth`` est **obligatoire** : le point d'entrée réseau ne sert jamais l'API en mode
    ouvert (``auth=None`` est réservé aux tests/compatibilité). Fonction isolée pour être
    testable — vérifier qu'elle produit bien une API qui **exige** un jeton.
    """
    from app.action_service import ActionService
    from app.action_store import ApplicationActionStore, OutboundMessageActionStore
    from app.decision_service import DecisionService
    from app.decision_store import DecisionStore
    from app.offer_store import OfferStore
    from app.profile_store import ProfileStore
    from app.recommendation_service import RecommendationService
    from hermes.orchestrator import HermesOrchestrator
    from hermes.run_store import RunStore

    if auth is None:
        raise ValueError("assemble_api exige un AuthProvider (pas de mode ouvert en prod)")

    decisions = DecisionService(DecisionStore(conn))
    orchestrator = HermesOrchestrator(
        RecommendationService(ProfileStore(conn), OfferStore(conn)),
        decisions,
        runs=RunStore(conn),
    )
    actions = ActionService(
        decisions, ApplicationActionStore(conn), OutboundMessageActionStore(conn)
    )
    return HermesApi(orchestrator, actions, auth)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ttl_to_expires_at(ttl_seconds: int, *, issued_at: datetime | None = None) -> str:
    """Échéance ISO 8601 = instant d'émission + ``ttl_seconds`` (émission = maintenant UTC)."""
    return ((issued_at or _utcnow()) + timedelta(seconds=ttl_seconds)).isoformat()


def parse_ttl_seconds(raw: str | None) -> int | None:
    """Valide ``OPPORTUNE_API_TOKEN_TTL`` : entier **strictement positif** de secondes, ou ``None``.

    ``None``/chaîne vide → ``None`` (jeton sans échéance, rétro-compat). Toute autre valeur
    non conforme (non entière, nulle ou négative) → ``ValueError`` explicite : on refuse de
    démarrer sur une échéance ambiguë plutôt que d'émettre un jeton mort-né ou de planter
    sur un ``int()`` brut. Cohérent avec le fail-fast du jeton manquant.
    """
    if raw is None or raw == "":
        return None
    try:
        ttl = int(raw)
    except ValueError:
        raise ValueError(
            f"OPPORTUNE_API_TOKEN_TTL invalide ({raw!r}) : entier positif de secondes attendu."
        ) from None
    if ttl <= 0:
        raise ValueError(
            f"OPPORTUNE_API_TOKEN_TTL invalide ({ttl}) : doit être strictement positif."
        )
    return ttl


def build_auth(
    token: str,
    owned_candidates,
    *,
    expires_at: str | None = None,
    now=None,
) -> AuthProvider:
    """Compose un ``AuthProvider`` mono-jeton (rôle ``reviewer``), échéance optionnelle.

    ``expires_at=None`` → jeton **sans expiration** (``User`` nu) ; sinon un ``TokenRecord``
    porteur de l'échéance. ``now`` (horloge de vérification) est transmis tel quel à
    ``AuthProvider``. Isolé de ``main`` pour être testable sans démarrer de serveur.
    """
    user = User(id="demo", role=REVIEWER, owned_candidates=frozenset(owned_candidates))
    record: User | TokenRecord = user if expires_at is None else TokenRecord(user, expires_at)
    kwargs = {} if now is None else {"now": now}
    return AuthProvider({token: record}, **kwargs)


def main() -> None:  # pragma: no cover - point d'entrée réseau, non testé
    import os

    from app.db import connect

    token = os.environ.get("OPPORTUNE_API_TOKEN")
    if not token:
        raise SystemExit(
            "OPPORTUNE_API_TOKEN manquant : l'API ne démarre jamais sans authentification."
        )
    owned = [c for c in os.environ.get("OPPORTUNE_API_CANDIDATES", "").split(",") if c]
    # Expiration réelle si OPPORTUNE_API_TOKEN_TTL (secondes) est fourni ; sinon jeton sans
    # échéance (rétro-compat). Câblage pur : toute la logique vit dans AuthProvider.
    try:
        ttl = parse_ttl_seconds(os.environ.get("OPPORTUNE_API_TOKEN_TTL"))
    except ValueError as err:
        raise SystemExit(str(err)) from err
    expires_at = _ttl_to_expires_at(ttl) if ttl is not None else None
    auth = build_auth(token, owned, expires_at=expires_at)

    server = create_server(assemble_api(connect(), auth))
    host, port = server.server_address
    print(f"API Hermes à l'écoute sur http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
