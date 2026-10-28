#!/usr/bin/env bash
#
# Construit le binaire autonome de l'API Opportune (OPP-190, PyInstaller).
#
# Produit un exécutable unique dans `python/dist/opportune-api` qui lance l'API
# HTTP sans Python ni venv installés. PyInstaller **ne fait pas** de
# cross-compilation : le binaire produit cible l'OS courant. Les binaires
# Windows/macOS se construisent sur ces OS (ou en CI — cf. OPP-194).
#
# Usage :
#   bash packaging/build-api.sh          # depuis python/
#
# Prérequis : l'extra `build` (PyInstaller) et les extras embarqués installés :
#   .venv/bin/pip install -e ".[build,scrape,pdf]"
set -euo pipefail

PY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PY_DIR"

# Interpréteur : venv local d'abord, puis venv activé, puis python du PATH.
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
else
  PYTHON="python3"
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "✗ PyInstaller introuvable pour $PYTHON." >&2
  echo "  Installer l'extra build : \"$PYTHON\" -m pip install -e \".[build,scrape,pdf]\"" >&2
  exit 1
fi

echo "→ Construction du binaire (PyInstaller)…"
"$PYTHON" -m PyInstaller --clean --noconfirm packaging/opportune-api.spec

echo "✓ Binaire prêt : $PY_DIR/dist/opportune-api"
