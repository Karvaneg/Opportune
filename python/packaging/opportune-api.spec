# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller — API Opportune en binaire autonome (OPP-190).

Produit un **binaire unique** (one-file) qui lance l'API HTTP sans Python ni
venv installés sur la machine cible. Construction : voir ``build-api.sh`` (ou
``pyinstaller packaging/opportune-api.spec`` depuis ``python/``).

Choix structurants :

- **Collecte exhaustive des sous-modules** ``app``, ``hermes`` et ``api`` : le
  cœur importe presque tout en différé (``from app.X import Y`` dans les corps
  de fonctions), que l'analyse statique de PyInstaller ne voit pas. Sans ça, le
  binaire planterait au premier import paresseux (``ModuleNotFoundError``).
- **Extras embarqués : scrape + pdf.** ``bs4``/``soupsieve`` (intake RSS & URL)
  et ``pypdf`` (import de CV) sont des endpoints réels de l'API → inclus en
  imports cachés. L'extra ``discord`` est **exclu** : la gateway Discord est un
  process séparé, pas servie par l'API HTTP, et ``discord.py`` alourdirait le
  binaire pour rien.
- Pas de ``datas`` : le schéma SQLite est créé en code (``CREATE TABLE IF NOT
  EXISTS``) et le seed démo est du Python pur — aucun fichier externe à joindre.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

# ``SPECPATH`` est le dossier contenant ce .spec (packaging/). Le code source
# vit dans ../src ; on l'ajoute au chemin de recherche pour que l'analyse et la
# collecte des sous-modules trouvent les packages du cœur.
SRC_DIR = os.path.join(SPECPATH, "..", "src")
ENTRY = os.path.join(SPECPATH, "api_entry.py")

hiddenimports = (
    collect_submodules("app", on_error="ignore")
    + collect_submodules("hermes", on_error="ignore")
    + collect_submodules("api", on_error="ignore")
    + ["bs4", "soupsieve", "pypdf"]
)

a = Analysis(
    [ENTRY],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # ``discord`` (extra non servi par l'API) : exclu pour ne pas gonfler le binaire.
    excludes=["discord"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="opportune-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
