#!/usr/bin/env bash
#
# Démarrage simplifié de l'API Hermes (OPP-153).
#
# Une seule commande : lit la configuration depuis `python/.env` (source unique,
# plus de variables à retaper à chaque lancement), auto-détecte `OLLAMA_HOST` sous
# WSL si besoin, puis lance `python -m api.server`.
#
# Usage :
#   bash scripts/serve-api.sh
#
# Prérequis : `python/.env` renseigné (au minimum OPPORTUNE_API_TOKEN). Modèle de
# configuration versionné (sans secret) : `python/.env.example`.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_DIR="$ROOT/python"
ENV_FILE="$PY_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "✗ $ENV_FILE introuvable." >&2
  echo "  Copier le modèle puis le renseigner : cp python/.env.example python/.env" >&2
  exit 1
fi

# Source unique : on exporte chaque clé=valeur de .env SANS sourcer le fichier.
# Sourcer (`. .env`) interpréterait $, `...` et $(...) comme du shell : un secret
# contenant « $ » serait silencieusement tronqué et un $(...) serait exécuté. On lit
# donc littéralement, en ne gardant que les lignes clé=valeur avec une clé valide.
while IFS='=' read -r key value || [ -n "$key" ]; do
  # Ignore lignes vides et commentaires (# en début de ligne, espaces tolérés).
  case "$key" in
    ''|[[:space:]]*'#'*|'#'*) continue ;;
  esac
  # Clé : on retire les espaces autour et on exige un identifiant d'environnement.
  key="${key#"${key%%[![:space:]]*}"}"
  key="${key%"${key##*[![:space:]]}"}"
  [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
  # Valeur : on retire d'éventuels guillemets englobants (comme le ferait dotenv),
  # sans aucune autre interprétation.
  value="${value%$'\r'}"
  case "$value" in
    \"*\") value="${value#\"}"; value="${value%\"}" ;;
    \'*\') value="${value#\'}"; value="${value%\'}" ;;
  esac
  export "$key=$value"
done < "$ENV_FILE"

# Le serveur refuse de démarrer sans jeton ; on le signale tôt, en pointant vers .env.
if [ -z "${OPPORTUNE_API_TOKEN:-}" ]; then
  echo "✗ OPPORTUNE_API_TOKEN manquant dans $ENV_FILE : l'API ne démarre jamais sans jeton." >&2
  exit 1
fi

# Le jeton ne possède alors aucun candidat : l'API démarre mais ne peut agir sur rien.
# Non bloquant (le serveur le tolère), mais on prévient — c'est presque toujours une
# config incomplète. Voir README « au minimum OPPORTUNE_API_TOKEN et …_CANDIDATES ».
if [ -z "${OPPORTUNE_API_CANDIDATES:-}" ]; then
  echo "⚠ OPPORTUNE_API_CANDIDATES vide : le jeton ne possédera aucun candidat." >&2
fi

# Auto-détection de l'hôte Ollama sous WSL : l'Ollama natif Windows est joignable via
# la passerelle (gateway) de l'adaptateur WSL, dont l'IP peut changer entre reboots.
# On ne détecte que si OLLAMA_HOST n'est pas déjà fixé dans .env (une valeur explicite prime).
if [ -z "${OLLAMA_HOST:-}" ] && grep -qi microsoft /proc/version 2>/dev/null; then
  # `|| true` : sans ça, `ip` absent/en échec ferait remonter un code non-zéro via
  # pipefail et `set -e` tuerait le script ici (stderr masqué → aucun message).
  gateway="$(ip route show default 2>/dev/null | awk '/default/ {print $3; exit}' || true)"
  if [ -n "$gateway" ]; then
    export OLLAMA_HOST="http://${gateway}:11434"
    echo "• OLLAMA_HOST auto-détecté (WSL) : $OLLAMA_HOST"
  fi
fi

# Interpréteur : venv local du projet d'abord, puis venv éventuellement activé
# (VIRTUAL_ENV), puis `python`/`python3` du PATH. Honorer VIRTUAL_ENV évite de
# retomber sur un python3 système qui n'a pas le package installé.
if [ -x "$PY_DIR/.venv/bin/python" ]; then
  PYTHON="$PY_DIR/.venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PYTHON="$VIRTUAL_ENV/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  PYTHON="python3"
fi

# Le package est en layout src/ : `python -m api.server` n'aboutit que s'il est
# installé (editable). On le vérifie tôt, sans effet de bord (find_spec n'exécute
# pas le module), pour un message clair plutôt qu'un ModuleNotFoundError au démarrage.
if ! "$PYTHON" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('api') else 1)" >/dev/null 2>&1; then
  echo "✗ Package 'opportune' introuvable pour $PYTHON (layout src/ non installé)." >&2
  echo "  Installer en editable : (cd python && \"$PYTHON\" -m pip install -e .)" >&2
  exit 1
fi

echo "• Candidats possédés : ${OPPORTUNE_API_CANDIDATES:-<aucun>}"
echo "• Base SQLite        : ${OPPORTUNE_DB_PATH:-data/opportune.db (défaut)}"
echo "• Ollama             : ${OLLAMA_HOST:-http://localhost:11434 (défaut)}"
echo "→ Démarrage de l'API…"

cd "$PY_DIR"
exec "$PYTHON" -m api.server
