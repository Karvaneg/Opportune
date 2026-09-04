"""Test de fumée : le package métier Python s'importe et s'exécute."""

from app import __version__, healthcheck


def test_package_importable():
    assert __version__ == "1.0.0"


def test_healthcheck_ok():
    assert healthcheck() == "ok"
