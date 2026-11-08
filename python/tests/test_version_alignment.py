"""La version d'Opportune est la même partout (OPP-246).

Source : ``frontend/package.json`` (affichée dans « À propos » et sur l'écran d'accueil, lue par
l'app de bureau via ``tauri.conf.json``). L'API, le paquet Python et la coquille Rust la
répètent ; ces tests échouent si l'un d'eux n'a pas suivi un changement de version.
"""

import json
import tomllib
from pathlib import Path

import pytest

from app import __version__

REPO = Path(__file__).resolve().parents[2]

# L'image Docker de test ne copie que `python/` : sans le front, rien à comparer.
pytestmark = pytest.mark.skipif(
    not (REPO / "frontend" / "package.json").exists(), reason="frontend/ absent (image Docker)"
)


def _package_json_version() -> str:
    return json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))["version"]


def test_tauri_reads_the_version_from_package_json():
    tauri_conf = json.loads(
        (REPO / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )

    assert tauri_conf["version"] == "../package.json"


def test_python_package_has_the_package_json_version():
    expected_version = _package_json_version()

    pyproject = tomllib.loads((REPO / "python" / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == expected_version


def test_api_reports_the_package_json_version():
    expected_version = _package_json_version()

    api_version = __version__

    assert api_version == expected_version


def test_rust_crate_has_the_package_json_version():
    expected_version = _package_json_version()

    cargo = tomllib.loads(
        (REPO / "frontend" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    )

    assert cargo["package"]["version"] == expected_version
