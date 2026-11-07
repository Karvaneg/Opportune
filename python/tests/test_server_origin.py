"""Tests de transport des contrôles ``Origin`` et ``Host`` (OPP-233).

On monte un vrai serveur sur un port éphémère (loopback) avec un dispatcher factice qui
enregistre les appels : une requête refusée doit rendre 403 **sans** atteindre le dispatcher.
"""

import pytest

from api.app import Response
from serve_once import serve_once


class _RecordingApi:
    """Dispatcher factice : note chaque appel et répond 200 (duck-typing HermesApi)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def dispatch(self, method, path, body, headers):
        self.calls.append((method, path))
        return Response(200, {"ok": True})


def _origin(template: str):
    """En-têtes portant ``Origin`` ; ``{port}`` est remplacé par le port d'écoute."""
    return lambda port: {"Origin": template.format(port=port)}


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_write_from_foreign_origin_is_refused_without_effect(method):
    api = _RecordingApi()

    status, body = serve_once(api, method, headers_for=_origin("https://evil.example"))

    assert status == 403
    assert "OPPORTUNE_EXTRA_ORIGINS" in body["error"]
    assert api.calls == []


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:{port}", "http://localhost:{port}", "http://[::1]:{port}"],
)
def test_write_from_api_origin_is_dispatched(origin):
    api = _RecordingApi()

    status, _ = serve_once(api, "POST", headers_for=_origin(origin))

    assert status == 200
    assert api.calls == [("POST", "/x")]


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://localhost:4173"])
def test_write_from_dev_front_is_dispatched_only_in_dev(origin):
    dev_api = _RecordingApi()
    packaged_api = _RecordingApi()

    dev_status, _ = serve_once(
        dev_api, "POST", headers_for=_origin(origin), allow_dev_front=True
    )
    packaged_status, _ = serve_once(packaged_api, "POST", headers_for=_origin(origin))

    assert dev_status == 200
    assert packaged_status == 403
    assert packaged_api.calls == []


def test_write_from_extra_origin_is_dispatched():
    api = _RecordingApi()

    status, _ = serve_once(
        api,
        "POST",
        headers_for=_origin("http://172.18.0.5:5173"),
        extra_origins=("http://172.18.0.5:5173",),
    )

    assert status == 200
    assert api.calls == [("POST", "/x")]


def test_write_without_origin_is_dispatched():
    api = _RecordingApi()

    status, _ = serve_once(api, "POST")

    assert status == 200
    assert api.calls == [("POST", "/x")]


def test_read_from_foreign_origin_is_not_blocked():
    # Le contrôle d'``Origin`` vise les écritures : une lecture n'a pas d'effet, et le
    # navigateur empêche déjà la page étrangère d'en lire la réponse (pas d'en-tête CORS).
    api = _RecordingApi()

    status, _ = serve_once(api, "GET", headers_for=_origin("https://evil.example"))

    assert status == 200
    assert api.calls == [("GET", "/x")]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
def test_request_with_foreign_host_is_refused_without_effect(method):
    # DNS rebinding : la page est « même site », mais le navigateur envoie son propre ``Host``.
    api = _RecordingApi()

    status, _ = serve_once(api, method, headers_for=lambda port: {"Host": f"evil.example:{port}"})

    assert status == 403
    assert api.calls == []


def test_static_request_with_foreign_host_is_refused(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    api = _RecordingApi()

    status, _ = serve_once(
        api,
        "GET",
        path="/",
        headers_for=lambda port: {"Host": f"evil.example:{port}"},
        static_dir=tmp_path,
    )

    assert status == 403
