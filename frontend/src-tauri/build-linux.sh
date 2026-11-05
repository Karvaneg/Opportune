#!/usr/bin/env bash
#
# Construit les bundles Linux d'Opportune (.deb / .rpm / .AppImage) — OPP-194.
#
# Un `tauri build` nu échoue sur l'étape **AppImage** (le .deb et le .rpm, eux, passent sans rien) :
#
#   1. `linuxdeploy` est distribué en AppImage et ne peut pas se monter via FUSE sous WSL/headless.
#      → APPIMAGE_EXTRACT_AND_RUN=1 lui fait s'extraire au lieu de se monter.
#   2. `linuxdeploy` inspecte les libs Ollama embarquées et tente de résoudre leur dépendance
#      interne `libggml-base.so.0` ; or ces libs se trouvent entre elles via un rpath `$ORIGIN`
#      qu'il n'honore pas → il la croit manquante et échoue.
#      → on la lui désigne via LD_LIBRARY_PATH pointé sur le dossier des libs Ollama.
#   3. NO_STRIP=1 évite un échec de `strip` de linuxdeploy sur certaines libs.
#
# Ce wrapper pose cet environnement puis délègue à `tauri build` (les arguments sont transmis, ex.
# `build-linux.sh --bundles deb` pour ne faire que le .deb).
#
# Usage :
#   bash src-tauri/build-linux.sh                 # depuis frontend/ — tous les bundles Linux
#   bash src-tauri/build-linux.sh --bundles deb   # seulement le .deb
#
# Prérequis : les deux sidecars en place (sync-sidecar.sh + sync-ollama.sh) et le front compilé.
set -euo pipefail

TAURI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLLAMA_LIB="$TAURI_DIR/binaries/ollama/lib/ollama"

if [ ! -d "$OLLAMA_LIB" ]; then
  echo "✗ Arbre Ollama absent ($OLLAMA_LIB). Lance d'abord sync-ollama.sh." >&2
  exit 1
fi

export APPIMAGE_EXTRACT_AND_RUN=1
export NO_STRIP=1
export LD_LIBRARY_PATH="$OLLAMA_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

cd "$TAURI_DIR/.."   # frontend/
exec npm run tauri build -- "$@"
