"""Helper de test : monte un vrai serveur HTTP sur un port éphémère et sert **une** requête.

Partagé par les tests de transport (``test_server_transport``, ``test_server_origin``) pour ne
pas dupliquer le montage serveur + thread + urllib.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from typing import Callable

from api.server import make_handler

# Construit les en-têtes de la requête à partir du port d'écoute (connu une fois lié).
HeadersFor = Callable[[int], dict[str, str]]


def serve_once(
    api,
    method: str = "POST",
    path: str = "/api/x",
    headers_for: HeadersFor | None = None,
    **handler_options,
) -> tuple[int, dict]:
    """Sert une requête ``method`` sur ``path`` avec ``api`` ; rend (status, corps JSON).

    ``handler_options`` est transmis à ``make_handler`` (``allow_dev_front``, ``extra_origins``…).
    """
    server = HTTPServer(("127.0.0.1", 0), make_handler(api, **handler_options))
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    port = server.server_address[1]
    headers = {"Content-Type": "application/json"}
    if headers_for is not None:
        headers.update(headers_for(port))
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=b"{}", method=method, headers=headers
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
