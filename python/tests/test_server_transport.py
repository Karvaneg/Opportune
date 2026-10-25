"""Tests du filet transport HTTP (OPP-207).

``make_handler`` ne doit **jamais** laisser une exception du dispatcher fermer la connexion
sans réponse (« empty reply from server ») : toute erreur devient une réponse JSON lisible.
On monte un vrai serveur sur un port éphémère (loopback, sans réseau externe) et on vérifie
les codes rendus selon l'exception levée par un dispatcher factice.
"""

import json
import sqlite3
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

from api.app import HermesApi
from api.server import make_handler
from app.db import connect
from app.offer import Offer
from app.offer_store import OfferStore


class _RaisingApi:
    """Dispatcher factice : lève l'exception fournie à chaque requête (duck-typing HermesApi)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def dispatch(self, method, path, body, headers):
        raise self._exc


def _post_once(api) -> tuple[int, dict]:
    """Sert **une** requête POST avec ``api`` et rend (status, corps JSON décodé)."""
    server = HTTPServer(("127.0.0.1", 0), make_handler(api))
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    port = server.server_address[1]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/x",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx sont des HTTPError côté client
        status, raw = exc.code, exc.read()
    finally:
        thread.join(timeout=2)
        server.server_close()
    return status, json.loads(raw)


def test_unexpected_exception_becomes_500_json():
    status, body = _post_once(_RaisingApi(RuntimeError("boom")))
    assert status == 500
    assert "error" in body


def test_database_locked_becomes_503_transient():
    status, body = _post_once(_RaisingApi(sqlite3.OperationalError("database is locked")))
    assert status == 503
    assert "error" in body


def test_other_operational_error_becomes_500():
    # Une OperationalError qui n'est pas un verrou reste une 500 (vraie anomalie).
    status, body = _post_once(_RaisingApi(sqlite3.OperationalError("no such table: offers")))
    assert status == 500
    assert "error" in body


class _PoisoningAuth:
    """Auth factice qui ouvre une transaction de lecture **puis lève** — reproduit une requête
    interrompue entre un ordre SQL et son commit (OPP-212), avant tout routage."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def authenticate(self, headers):
        self._conn.execute("BEGIN")
        self._conn.execute("SELECT COUNT(*) FROM offers").fetchone()  # épingle un snapshot WAL
        raise RuntimeError("interruption avant commit")


def _offer(offer_id: str) -> Offer:
    return Offer(
        id=offer_id, title="Dev", company="ACME", location="Paris", skills=["python"],
        seniority="junior", contract_type="CDI", summary="s", attention_points=[],
        source="adzuna", url=f"https://example.test/{offer_id}", raw_text="texte",
    )


def test_dispatch_rollback_unpoisons_shared_connection(tmp_path):
    """OPP-212 : une requête interrompue entre un ordre SQL et son commit ne doit pas laisser la
    connexion partagée épinglée sur un vieux snapshot (lectures périmées : offres de collecte
    invisibles même après rechargement). ``dispatch`` referme la transaction en fin de requête.

    Sans le correctif : la transaction de lecture reste ouverte → la connexion est figée et ne
    voit jamais l'offre écrite par une autre connexion (le job de collecte), d'où le test rouge.
    """
    db = str(tmp_path / "offers.db")
    conn = connect(db)
    OfferStore(conn)  # crée la table offers (+ commit) ; connexion propre

    api = HermesApi(object(), auth=_PoisoningAuth(conn), conn=conn)

    # Une requête échoue APRÈS avoir ouvert une transaction de lecture (snapshot épinglé).
    resp = api.dispatch("GET", "/offers", {}, {})
    assert resp.status == 500
    # Invariant OPP-212 : plus aucune transaction ouverte sur la connexion partagée.
    assert conn.in_transaction is False

    # Une autre connexion (comme le job de collecte asynchrone) persiste une offre.
    other = connect(db)
    OfferStore(other).save(_offer("job-1"))
    other.close()

    # La connexion de l'API n'est pas figée : elle voit bien l'offre écrite ailleurs.
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 1
