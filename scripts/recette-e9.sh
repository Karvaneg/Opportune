#!/usr/bin/env bash
#
# Recette finale de l'Epic E9 (consultation Hermes) — parcours bout-en-bout.
#
# Vérifie, contre l'API réelle (via le proxy Vite du front), les cas :
#   login → /me · liste /runs · pagination · détail · recommandations
#   · erreurs 401/404 · accès direct par ID.
#
# Prérequis : la démo Docker tourne (front sur :5173, API sur le réseau opp-demo).
#   Voir README.md § « Démarrage » / handoff pour (re)monter la démo.
#
# Usage :
#   bash scripts/recette-e9.sh                 # cible http://localhost:5173/api, token demo-token
#   BASE=http://localhost:8000 TOKEN=xxx bash scripts/recette-e9.sh   # cible directe l'API
#
set -u

BASE="${BASE:-http://localhost:5173/api}"
TOKEN="${TOKEN:-demo-token}"
BAD_TOKEN="${BAD_TOKEN:-jeton-invalide}"

pass=0
fail=0

# code HTTP d'une requête ($1=libellé, $2=code attendu, reste=args curl)
check_code() {
  local label="$1" want="$2"; shift 2
  local got
  got=$(curl -s -o /dev/null -w "%{http_code}" "$@")
  if [ "$got" = "$want" ]; then
    printf '  \033[32m✓\033[0m %s (HTTP %s)\n' "$label" "$got"; pass=$((pass+1))
  else
    printf '  \033[31m✗\033[0m %s (attendu %s, obtenu %s)\n' "$label" "$want" "$got"; fail=$((fail+1))
  fi
}

# vérifie qu'un corps JSON satisfait une expression python ($1=libellé, $2=json, $3=expr sur `d`)
check_json() {
  local label="$1" json="$2" expr="$3"
  if printf '%s' "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if ($expr) else 1)" 2>/dev/null; then
    printf '  \033[32m✓\033[0m %s\n' "$label"; pass=$((pass+1))
  else
    printf '  \033[31m✗\033[0m %s — corps: %s\n' "$label" "$json"; fail=$((fail+1))
  fi
}

json_get() { printf '%s' "$1" | python3 -c "import sys,json; d=json.load(sys.stdin); print($2)" 2>/dev/null; }

AUTH=(-H "Authorization: Bearer $TOKEN")
BAD=(-H "Authorization: Bearer $BAD_TOKEN")

echo "== Recette E9 — cible $BASE =="

echo "[1] login → /me"
check_code "sans jeton → 401" 401 "$BASE/me"
check_code "mauvais jeton → 401" 401 "${BAD[@]}" "$BASE/me"
check_code "bon jeton → 200" 200 "${AUTH[@]}" "$BASE/me"
ME=$(curl -s "${AUTH[@]}" "$BASE/me")
check_json "identité complète {id,role,owned_count}" "$ME" "d.get('id') and 'role' in d and 'owned_count' in d"

echo "[2] liste /runs"
RUNS=$(curl -s "${AUTH[@]}" "$BASE/runs?page=1")
check_json "enveloppe paginée {items,page,total,total_pages}" "$RUNS" "all(k in d for k in ('items','page','page_size','total','total_pages'))"
check_json "au moins un run dans le périmètre" "$RUNS" "len(d['items'])>=1"
check_json "résumé sans détail (evaluation_count présent, pas d'evaluations)" "$RUNS" "'evaluation_count' in d['items'][0] and 'evaluations' not in d['items'][0]"
RUN_ID=$(json_get "$RUNS" "d['items'][0]['run_id']")
TOTAL=$(json_get "$RUNS" "d['total']")
echo "    run cible : $RUN_ID (total=$TOTAL)"

echo "[3] pagination (/runs?page_size=2)"
P1=$(curl -s "${AUTH[@]}" "$BASE/runs?page=1&page_size=2")
check_json "page 1 : total_pages = ceil(total/2)" "$P1" "d['total_pages']==((d['total']+1)//2)"
check_json "page 1 : au plus 2 items" "$P1" "len(d['items'])<=2"
BEYOND=$(curl -s "${AUTH[@]}" "$BASE/runs?page=999&page_size=2")
check_json "page hors borne : items vides, total conservé" "$BEYOND" "d['items']==[] and d['total']==$TOTAL"
check_code "page=0 → 400" 400 "${AUTH[@]}" "$BASE/runs?page=0"

echo "[4] détail d'un run (/runs/{id})"
check_code "détail run existant → 200" 200 "${AUTH[@]}" "$BASE/runs/$RUN_ID"
DET=$(curl -s "${AUTH[@]}" "$BASE/runs/$RUN_ID")
check_json "détail porte run_id + evaluations" "$DET" "d.get('run_id')=='$RUN_ID' and 'evaluations' in d"

echo "[5] recommandations paginées (/runs/{id}/recommendations)"
REC=$(curl -s "${AUTH[@]}" "$BASE/runs/$RUN_ID/recommendations?page=1&page_size=1")
check_json "enveloppe paginée" "$REC" "all(k in d for k in ('items','page','page_size','total','total_pages'))"
check_json "items portent recommendation_id" "$REC" "(len(d['items'])==0) or ('recommendation_id' in d['items'][0])"
check_code "decision_status invalide → 400" 400 "${AUTH[@]}" "$BASE/runs/$RUN_ID/recommendations?decision_status=WAT"

echo "[6] erreurs 401 / 404"
check_code "/runs sans jeton → 401" 401 "$BASE/runs"
check_code "détail run inexistant → 404" 404 "${AUTH[@]}" "$BASE/runs/run-inexistant-xyz"
check_code "recommandations run inexistant → 404" 404 "${AUTH[@]}" "$BASE/runs/run-inexistant-xyz/recommendations"
NF=$(curl -s "${AUTH[@]}" "$BASE/runs/run-inexistant-xyz")
check_json "404 message neutre (anti-énumération, pas de 'n'existe pas')" "$NF" "'introuvable' in d.get('error','')"

echo "[7] accès direct par ID (deep-link)"
check_code "accès direct au détail par ID → 200" 200 "${AUTH[@]}" "$BASE/runs/$RUN_ID"
check_code "accès direct aux recommandations par ID → 200" 200 "${AUTH[@]}" "$BASE/runs/$RUN_ID/recommendations"

echo
echo "== Résultat : $pass OK / $fail KO =="
[ "$fail" -eq 0 ]
