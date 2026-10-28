#!/usr/bin/env bash
#
# Construit le binaire autonome d'Opportune (OPP-190/191, PyInstaller).
#
# Produit un exécutable unique dans `python/dist/opportune-api` qui sert le
# **front compilé + l'API** sur localhost, sans Python, venv ni Node installés
# (OPP-191 : un binaire = app complète). PyInstaller **ne fait pas** de
# cross-compilation : le binaire produit cible l'OS courant. Les binaires
# Windows/macOS se construisent sur ces OS (ou en CI — cf. OPP-194).
#
# Usage :
#   bash packaging/build-api.sh          # depuis python/
#
# Prérequis : l'extra `build` (PyInstaller) et les extras embarqués installés :
#   .venv/bin/pip install -e ".[build,scrape,pdf]"
# Le front est (re)construit automatiquement ci-dessous ; Node/npm requis pour ça.
set -euo pipefail

PY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$(cd "$PY_DIR/../frontend" && pwd)"
cd "$PY_DIR"

# Front compilé embarqué dans le binaire (OPP-191) : on le (re)construit d'abord pour
# garantir des assets à jour. `npm run build` lance `tsc -b && vite build`.
echo "→ Construction du front (npm run build)…"
( cd "$FRONTEND_DIR" && npm run build )

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
