"""Test de fumée : l'ossature du projet Python s'importe et s'exécute (OPP-070)."""

from app import __version__, healthcheck


def test_package_importable():
    assert __version__ == "0.1.0"


def test_healthcheck_ok():
    assert healthcheck() == "ok"
