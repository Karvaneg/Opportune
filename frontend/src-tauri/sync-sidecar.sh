#!/usr/bin/env bash
#
# Place le binaire API (OPP-190) là où Tauri attend son sidecar (OPP-192).
#
# Tauri résout un sidecar sous `binaries/<nom>-<triple-cible>` (ex.
# `binaries/opportune-api-x86_64-unknown-linux-gnu`). Ce script construit le binaire
# via packaging/build-api.sh puis le copie sous le nom attendu pour l'OS courant.
#
# Usage :
#   bash src-tauri/sync-sidecar.sh      # depuis frontend/
#
# Prérequis : rustc (pour connaître le triple) et le toolchain de build-api.sh.
set -euo pipefail

TAURI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TAURI_DIR/../.." && pwd)"
PY_DIR="$REPO_ROOT/python"

# Triple de la cible courante, tel que Tauri le nomme (ex. x86_64-unknown-linux-gnu).
if ! command -v rustc >/dev/null 2>&1; then
  echo "✗ rustc introuvable : installe Rust (rustup) d'abord." >&2
  exit 1
fi
TRIPLE="$(rustc -vV | awk '/^host:/ {print $2}')"

echo "→ Construction du binaire API…"
bash "$PY_DIR/packaging/build-api.sh"

SRC="$PY_DIR/dist/opportune-api"
EXT=""
case "$TRIPLE" in
  *windows*) EXT=".exe"; SRC="$SRC.exe" ;;
esac

DEST="$TAURI_DIR/binaries/opportune-api-$TRIPLE$EXT"
mkdir -p "$TAURI_DIR/binaries"
cp "$SRC" "$DEST"
chmod +x "$DEST" 2>/dev/null || true

echo "✓ Sidecar en place : $DEST"
