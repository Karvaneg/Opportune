#!/usr/bin/env bash
#
# generate-ai-context.sh
# ----------------------
# Génère .claude/skills/project-context.md : un instantané du projet destiné à fournir à
# Claude Code un contexte fiable et reproductible.
#
# Contenu : pile technique (back Python, front React/Vite, app de bureau Tauri), dépendances
# lues dans pyproject.toml, package.json et Cargo.toml, fichiers de configuration, et
# arborescence des fichiers **versionnés** (git ls-files : ni venvs, ni builds, ni fichiers
# personnels hors dépôt). Le prototype Node.js archivé (legacy/) est résumé en une ligne.
#
# Prérequis : git et python3 (3.11+, pour tomllib).
# Usage : bash scripts/generate-ai-context.sh

set -euo pipefail

# Racine du projet = parent du dossier contenant ce script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR=".claude/skills"
OUT_FILE="$OUT_DIR/project-context.md"
mkdir -p "$OUT_DIR"

GEN_DATE="$(date '+%Y-%m-%d %H:%M:%S %z')"

# --- Pile technique et dépendances -----------------------------------------------------------
# Lecture des manifestes en Python (tomllib, json) : plus fiable qu'un grep sur du TOML.
stack_and_deps="$(python3 - <<'PY'
import json
import tomllib
from pathlib import Path

stack, deps = [], []

pyproject = Path("python/pyproject.toml")
if pyproject.exists():
    project = tomllib.loads(pyproject.read_text())["project"]
    stack.append(f"Back Python {project.get('requires-python', '')} (`python/`, "
                 "bibliothèque standard)")
    deps.append("### Back : `python/pyproject.toml`\n")
    runtime = project.get("dependencies") or []
    deps.append(f"- **Production** : {', '.join(runtime) if runtime else 'aucune'}")
    for extra, items in project.get("optional-dependencies", {}).items():
        deps.append(f"- **Extra `{extra}`** : {', '.join(items)}")
    deps.append("")

package = Path("frontend/package.json")
if package.exists():
    data = json.loads(package.read_text())
    every = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    tools = [name for name in ("react", "vite", "typescript", "tailwindcss",
                               "@tanstack/react-query", "vitest", "@playwright/test")
             if name in every]
    stack.append("Front " + ", ".join(f"{name} {every[name]}" for name in tools)
                 + " (`frontend/`)")
    for section, title in (("dependencies", "Production"), ("devDependencies", "Développement")):
        items = data.get(section, {})
        if items:
            if title == "Production":
                deps.append("### Front : `frontend/package.json`\n")
            deps.append(f"- **{title}** : "
                        + ", ".join(f"{name} {version}" for name, version in items.items()))
    scripts = data.get("scripts", {})
    if scripts:
        deps.append("- **Scripts npm** : " + ", ".join(f"`{name}`" for name in scripts))
    deps.append("")

cargo = Path("frontend/src-tauri/Cargo.toml")
if cargo.exists():
    manifest = tomllib.loads(cargo.read_text())
    crates = manifest.get("dependencies", {})
    version = lambda spec: spec if isinstance(spec, str) else spec.get("version", "?")
    stack.append(f"App de bureau Tauri {version(crates.get('tauri', '?'))} "
                 "(`frontend/src-tauri/`, Rust)")
    deps.append("### App de bureau : `frontend/src-tauri/Cargo.toml`\n")
    deps.append("- **Crates** : "
                + ", ".join(f"{name} {version(spec)}" for name, spec in crates.items()))
    # Dépendances propres à une plateforme : [target.'cfg(unix)'.dependencies], etc.
    for target, table in manifest.get("target", {}).items():
        platform_crates = table.get("dependencies", {})
        if platform_crates:
            deps.append(f"- **Crates `{target}`** : "
                        + ", ".join(f"{n} {version(s)}" for n, s in platform_crates.items()))
    deps.append("")

print("STACK=" + " · ".join(stack) if stack else "STACK=Non détectée")
print("\n".join(deps).rstrip())
PY
)"
stack_line="$(printf '%s\n' "$stack_and_deps" | sed -n '1s/^STACK=//p')"
deps_output="$(printf '%s\n' "$stack_and_deps" | sed '1d')"
[ -z "$deps_output" ] && deps_output="(aucun manifeste trouvé)"

# --- Fichiers de configuration ---------------------------------------------------------------
# Fichiers versionnés de configuration à la racine, dans python/, frontend/ et src-tauri/.
config_output="$(
  git ls-files \
    | grep -E '^([^/]+|python/[^/]+|frontend/[^/]+|frontend/src-tauri/[^/]+|\.github/workflows/[^/]+)$' \
    | grep -E '(\.(json|toml|ya?ml|cfg|ini)$|(^|/)(Dockerfile|Makefile|\.env\.example|\.gitignore|vite\.config\.ts|playwright\.config\.ts))$' \
    | grep -v 'package-lock\.json$' \
    | sort
)"
[ -z "$config_output" ] && config_output="(aucun fichier de configuration détecté)"

# --- Arborescence (fichiers versionnés) ------------------------------------------------------
legacy_count="$(git ls-files legacy | wc -l | tr -d ' ')"
tree_output="$(git ls-files | grep -v '^legacy/' | sort)"

# --- Écriture du fichier de contexte ---------------------------------------------------------
{
  echo "# Contexte projet"
  echo ""
  echo "> Fichier généré automatiquement par \`scripts/generate-ai-context.sh\`."
  echo "> **Ne pas éditer à la main** : toute modification sera écrasée à la prochaine génération."
  echo ""
  echo "- **Date de génération :** $GEN_DATE"
  echo "- **Pile détectée :** $stack_line"
  echo ""
  echo "## Dépendances"
  echo ""
  echo "$deps_output"
  echo ""
  echo "## Fichiers de configuration"
  echo ""
  echo '```'
  echo "$config_output"
  echo '```'
  echo ""
  echo "## Arborescence (fichiers versionnés)"
  echo ""
  echo "_Source : \`git ls-files\`. Le prototype Node.js archivé \`legacy/\` ($legacy_count fichiers) est omis._"
  echo ""
  echo '```'
  echo "$tree_output"
  echo '```'
} > "$OUT_FILE"

echo "Contexte généré : $OUT_FILE"
