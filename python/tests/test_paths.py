"""Tests de la résolution du répertoire de données (OPP-190).

``user_data_dir`` arbitre entre trois cas : override explicite, binaire gelé
(par OS) et défaut historique. On force ``sys.frozen``/``sys.platform`` et les
variables d'environnement pour couvrir chaque branche sans vrai binaire.
"""

from pathlib import Path

from app.paths import user_data_dir


def _clear_data_env(monkeypatch):
    """Neutralise les variables d'environnement qui influencent la résolution."""
    for name in ("OPPORTUNE_DATA_DIR", "APPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)


def test_default_is_relative_data_dir_when_not_frozen(monkeypatch):
    _clear_data_env(monkeypatch)
    monkeypatch.delattr("sys.frozen", raising=False)

    assert user_data_dir() == Path("data")


def test_env_override_wins_even_when_frozen(monkeypatch):
    _clear_data_env(monkeypatch)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setenv("OPPORTUNE_DATA_DIR", "/tmp/opportune-custom")

    assert user_data_dir() == Path("/tmp/opportune-custom")


def test_frozen_linux_uses_xdg_data_home(monkeypatch):
    _clear_data_env(monkeypatch)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", "/home/u/.local/share")

    assert user_data_dir() == Path("/home/u/.local/share/opportune")


def test_frozen_windows_uses_appdata(monkeypatch):
    _clear_data_env(monkeypatch)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\u\AppData\Roaming")

    assert user_data_dir() == Path(r"C:\Users\u\AppData\Roaming") / "Opportune"


def test_frozen_macos_uses_application_support(monkeypatch):
    _clear_data_env(monkeypatch)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: Path("/Users/u")))

    assert user_data_dir() == Path("/Users/u/Library/Application Support/Opportune")
