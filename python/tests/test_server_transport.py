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

from api.server import make_handler


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
