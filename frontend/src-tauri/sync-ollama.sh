#!/usr/bin/env bash
#
# Embarque une version CPU seule d'Ollama pour le sidecar desktop (OPP-194).
#
# Les releases Ollama Linux officielles sont des archives .tar.zst d'environ 1,5 Go, car elles
# contiennent les runners GPU (CUDA v12/v13, ROCm, Vulkan) en plus du CPU. Pour un modèle 3B sur
# la machine d'un non-dev, le GPU est inutile : on télécharge l'archive, on **jette les runners
# GPU** (`lib/ollama/cuda_*`, `lib/ollama/rocm*`, `lib/ollama/vulkan*`) et on ne garde que
# `bin/ollama` + les libs CPU. Résultat attendu : ~115 Mo au lieu de 1,5 Go.
#
# L'arbre est déposé sous `src-tauri/binaries/ollama/` (voisins `bin/` et `lib/`, comme l'attend le
# binaire pour résoudre ses runners). Il est ensuite embarqué comme ressource Tauri
# (cf. tauri.conf.json → bundle.resources) et démarré par `src/main.rs`.
#
# Usage :
#   bash src-tauri/sync-ollama.sh            # depuis frontend/
#
# Prérequis : rustc (triple cible), curl, tar, et zstd (Debian/Ubuntu : sudo apt-get install zstd).
set -euo pipefail

# Version figée : on contrôle exactement quel moteur tourne, testé avec ministral-3:3b.
OLLAMA_VERSION="${OLLAMA_VERSION:-v0.40.13}"

TAURI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$TAURI_DIR/binaries/ollama"

# --- Outils requis -----------------------------------------------------------
for tool in curl tar rustc; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "✗ $tool introuvable." >&2
    exit 1
  fi
done
if ! command -v zstd >/dev/null 2>&1; then
  echo "✗ zstd introuvable : installe-le d'abord (Debian/Ubuntu : sudo apt-get install zstd)." >&2
  exit 1
fi

# --- Cible (OS + architecture) ----------------------------------------------
TRIPLE="$(rustc -vV | awk '/^host:/ {print $2}')"
case "$TRIPLE" in
  *linux*)   OS="linux" ;;
  *)         echo "✗ Cet OS ($TRIPLE) n'est pas encore géré par ce script (Linux seulement pour l'instant)." >&2
             echo "  Windows se traite sur l'hôte Windows ; Mac est reporté (OPP-216)." >&2
             exit 1 ;;
esac
case "$TRIPLE" in
  x86_64-*)  ARCH="amd64" ;;
  aarch64-*) ARCH="arm64" ;;
  *)         echo "✗ Architecture non gérée : $TRIPLE" >&2; exit 1 ;;
esac

ASSET="ollama-${OS}-${ARCH}.tar.zst"
URL="https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/${ASSET}"

# --- Téléchargement + extraction dans un dossier temporaire ------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ Téléchargement d'Ollama ${OLLAMA_VERSION} (${ASSET}, ~1,5 Go)…"
curl --fail --show-error --location --progress-bar "$URL" | zstd -d | tar -xf - -C "$TMP"

if [ ! -f "$TMP/bin/ollama" ]; then
  echo "✗ Structure inattendue : bin/ollama absent de l'archive." >&2
  exit 1
fi

# --- Élagage des runners GPU -------------------------------------------------
echo "→ Suppression des runners GPU (CUDA/ROCm/Vulkan)…"
if [ -d "$TMP/lib/ollama" ]; then
  find "$TMP/lib/ollama" -maxdepth 1 -type d \( -name 'cuda*' -o -name 'rocm*' -o -name 'vulkan*' \) -prune -exec rm -rf {} +
  # Le runner Vulkan peut aussi être un fichier (libggml-vulkan.so) directement sous lib/ollama.
  find "$TMP/lib/ollama" -maxdepth 1 -type f -name '*vulkan*' -delete
fi

# --- Dépôt de l'arbre CPU ----------------------------------------------------
rm -rf "$DEST"
mkdir -p "$DEST"
cp -a "$TMP/bin" "$DEST/bin"
[ -d "$TMP/lib" ] && cp -a "$TMP/lib" "$DEST/lib"
chmod +x "$DEST/bin/ollama" 2>/dev/null || true

echo "✓ Ollama CPU en place : $DEST ($(du -sh "$DEST" | cut -f1))"
