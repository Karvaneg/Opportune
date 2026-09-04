# Opportune — back Python (V2)

Cœur métier de la V2 d'Opportune : analyse d'offres, scoring, recommandation, décisions
et actions sensibles, orchestrés par **Hermes** et exposés via une **API HTTP**. C'est la
stack cible du projet (le V1 Node.js à la racine est historique — voir le README racine).

**Zéro dépendance de production** : tout le métier, l'orchestrateur et l'API sont écrits
avec la **bibliothèque standard** (`sqlite3`, `urllib`, `http.server`). Seul `pytest` est
requis, et seulement pour les tests.

## Les trois couches

```
src/
├── app/       Métier + persistance (fonctions pures + services + dépôts SQLite)
├── hermes/    Orchestrateur : enchaîne les services du métier en une boucle
└── api/       API HTTP : adaptateur mince exposant Hermes (dispatcher + serveur socket)
```

- **`app/`** — les briques métier, chacune à responsabilité unique : ingestion et
  normalisation d'offres (`offer_*`), profil candidat (`candidate_profile`, `profile_store`),
  matching/scoring/recommandation (`offer_profile_match`, `offer_score`,
  `recommendation_service`), décision et sa validation humaine (`decision*`), actions
  sensibles (`action*`), plus l'accès SQLite (`db`), le LLM (`llm`, `llm_client`) et
  l'authentification (`auth`). Les fonctions pures sont séparées des services (qui
  orchestrent + persistent) et des dépôts (persistance).
- **`hermes/`** — `HermesOrchestrator` **coordonne** ces services (il ne réimplémente
  aucune logique) : d'un `candidate_id`, il déroule `recommandation → décisions persistées`,
  journalise chaque exécution (`run_store`, modèles dans `models.py`) et offre le point
  d'entrée de la validation humaine.
- **`api/`** — `HermesApi.dispatch(method, path, body, headers)` route une requête vers
  l'orchestrateur et rend une `Response` **sans dépendre du transport** (donc testable sans
  réseau) ; `server.py` n'en est que l'adaptateur socket (`http.server`).

### Endpoints exposés

| Méthode & route | Rôle |
|---|---|
| `GET /me` | Sonde d'authentification + identité (`{id, role, owned_count}`) |
| `GET /runs` | Listing paginé des runs du périmètre (candidats possédés) |
| `GET /runs/{run_id}` | Détail d'un run (évaluations, erreurs) |
| `GET /runs/{run_id}/recommendations` | Recommandations paginées + filtres `advisory_status`/`decision_status` |
| `POST /candidates/{candidate_id}/recommendations` | Lance une recommandation |
| `GET /recommendations/{recommendation_id}` | Détail d'une recommandation |
| `POST /recommendations/{recommendation_id}/decision` | Validation humaine (rôle `reviewer`) |
| `POST /applications/{recommendation_id}/confirm` | Action sensible : candidature (confirmation explicite + décision `approved` + rôle `reviewer`) |
| `POST /messages/{contact_id}/confirm` | Action sensible : message (mêmes gardes) |

Gardes de sécurité communes : `Authorization: Bearer` valide (401 sinon), puis
**propriété** de la ressource et, pour les actions réservées, **rôle `reviewer`** (403).
Les 404 sont **neutres** : « inexistant » et « hors périmètre » sont indistinguables
(anti-énumération).

## Prérequis

- **Python ≥ 3.11** (ou **Docker**, chemin recommandé — notamment sous WSL2).

## Installation

Depuis `python/`, créer un environnement virtuel et installer le projet + ses dépendances
de développement :

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
```

## Exécution des tests

```bash
pytest
```

La suite couvre chaque brique métier, l'orchestrateur et l'API (services, pagination,
filtres, auth, décisions, actions), sans réseau : LLM injecté et dépôts SQLite en mémoire.

## Lancer l'API

Le serveur **refuse de démarrer sans jeton** (`OPPORTUNE_API_TOKEN`) : l'API n'est jamais
exposée sans authentification.

```bash
cd python
export OPPORTUNE_API_TOKEN=mon-jeton          # requis
export OPPORTUNE_API_CANDIDATES=cand-marie    # périmètre : candidats possédés (CSV)
export OPPORTUNE_DB_PATH=data/opportune.db     # base SQLite (défaut : data/opportune.db)
# export OPPORTUNE_API_TOKEN_TTL=3600          # optionnel : expiration du jeton (secondes)

python -m api.server                           # écoute sur http://127.0.0.1:8000
```

Le frontend React (`../frontend`) consomme cette API via un proxy `/api` (cf.
`frontend/README.md`). Recette de bout en bout : `bash ../scripts/recette-e9.sh`.

## Environnement Docker / WSL

Conteneur reproductible (OPP-071). Le code (`src/`, `tests/`) est monté en volume : les
modifications sont prises en compte sans reconstruire l'image.

### Avec Docker seul

```bash
cd python
docker build -t opportune-py:dev .
docker run --rm opportune-py:dev      # lance la suite de tests
```

### Avec Docker Compose (développement)

```bash
cd python
docker compose run --rm app            # lance pytest (commande par défaut)
docker compose run --rm app python -c "import app; print(app.healthcheck())"
```

## Base de données SQLite

Accès configuré via la bibliothèque standard (`sqlite3`) — **aucun ORM**.

- Chemin par défaut : `data/opportune.db`, surchargeable par `OPPORTUNE_DB_PATH`
  (`:memory:` accepté pour les tests).
- `app.db.connect()` ouvre une connexion configurée (lignes `sqlite3.Row`, clés étrangères
  activées) et crée le dossier parent au besoin.
- Sous Docker Compose, la base est persistée dans le volume `opportune-data`.

```python
from app.db import connect, healthcheck

conn = connect()            # data/opportune.db (ou OPPORTUNE_DB_PATH)
assert healthcheck(conn)    # SELECT 1
conn.close()
```

## LLM local — Ollama / Ministral

Accès au modèle via un client minimal (`app.llm` / `app.llm_client`) qui parle l'API HTTP
d'Ollama avec `urllib` — **aucune dépendance**. Le transport est **injectable** : les tests
n'ont besoin d'aucun serveur Ollama.

- `OLLAMA_HOST` (défaut `http://localhost:11434`) et `OLLAMA_MODEL` (défaut `ministral`)
  sont surchargeables par variables d'environnement.
- Sous Docker Compose, l'app pointe sur le service `ollama` ; les modèles sont persistés
  dans le volume `ollama-models`.

```bash
cd python
docker compose up -d ollama                       # démarre le serveur Ollama
docker compose exec ollama ollama pull ministral  # télécharge le modèle (une fois)
```

### Sous Windows / WSL2

- Installer **Docker Desktop** avec le backend **WSL2**, ou le moteur Docker directement
  dans la distribution WSL.
- Travailler depuis le système de fichiers Linux de WSL (par ex. `~/Opportune`) plutôt que
  `/mnt/c/...` : les montages de volumes y sont nettement plus rapides.
