#!/usr/bin/env bash
#
# generate-ai-context.sh
# ----------------------
# Genere .claude/skills/project-context.md : un instantane du projet destine
# a fournir a Claude Code un contexte fiable et reproductible.
#
# Point de depart minimal (stack non detectee : fallback shell).
# A adapter au projet a mesure qu'une stack se dessine (voir les TODO ci-dessous).
#
# Usage : bash scripts/generate-ai-context.sh

set -euo pipefail

# Racine du projet = parent du dossier contenant ce script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR=".claude/skills"
OUT_FILE="$OUT_DIR/project-context.md"
mkdir -p "$OUT_DIR"

# Dossiers exclus du scan d'arborescence.
EXCLUDES=(node_modules .git dist build .claude coverage)

# Construit les arguments de pruning pour `find`.
PRUNE_ARGS=()
for dir in "${EXCLUDES[@]}"; do
  PRUNE_ARGS+=(-name "$dir" -o)
done
# Retire le dernier "-o".
unset 'PRUNE_ARGS[${#PRUNE_ARGS[@]}-1]'

GEN_DATE="$(date '+%Y-%m-%d %H:%M:%S %z')"

# --- Arborescence -----------------------------------------------------------
tree_output="$(
  find . \( "${PRUNE_ARGS[@]}" \) -prune -o -print \
    | sed 's|^\./||' \
    | grep -v '^\.$' \
    | sort
)"

# --- Fichiers de configuration racine ---------------------------------------
# TODO: affiner selon la stack reelle une fois celle-ci connue.
config_output="$(
  find . -maxdepth 1 -type f \
    \( -name '*.json' -o -name '*.toml' -o -name '*.yaml' -o -name '*.yml' \
       -o -name '*.cfg' -o -name '*.ini' -o -name '.env*' -o -name 'Makefile' \) \
    | sed 's|^\./||' \
    | sort
)"
[ -z "$config_output" ] && config_output="(aucun fichier de configuration racine detecte)"

# --- Ecriture du fichier de contexte ----------------------------------------
{
  echo "# Contexte projet"
  echo ""
  echo "> Fichier genere automatiquement par \`scripts/generate-ai-context.sh\`."
  echo "> **Ne pas editer a la main** : toute modification sera ecrasee a la prochaine generation."
  echo ""
  echo "- **Date de generation :** $GEN_DATE"
  echo "- **Stack detectee :** Non detectee (fallback shell)"
  echo ""
  echo "## Dependances"
  echo ""
  # TODO: renseigner les dependances une fois un gestionnaire de paquets adopte
  #       (package.json, requirements.txt, Cargo.toml, etc.).
  echo "(aucune stack detectee — section a completer manuellement)"
  echo ""
  echo "## Fichiers de configuration racine"
  echo ""
  echo '```'
  echo "$config_output"
  echo '```'
  echo ""
  echo "## Arborescence"
  echo ""
  echo "_Exclusions : ${EXCLUDES[*]}_"
  echo ""
  echo '```'
  echo "$tree_output"
  echo '```'
} > "$OUT_FILE"

echo "Contexte genere : $OUT_FILE"
