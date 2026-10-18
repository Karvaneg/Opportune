# Opportune

Assistant de candidature : analyse d'offres, scoring, personnalisation et suivi, avec
validation humaine avant toute action sortante.

Le projet est en **migration V1 → V2** :

- **V2 (Python) — active.** Le moteur métier, l'orchestrateur **Hermes**, l'API HTTP et
  un **frontend web de consultation** (React/Vite). C'est là que se fait le développement
  courant. Code sous `python/` et `frontend/`.
- **V1 (Node.js) — historique.** Le MVP CLI d'origine (intégration Notion, stockage JSON)
  vit encore à la racine (`src/`, `index.js`, `package.json`). Conservé comme référence le
  temps de la migration ; il n'est plus la cible produit.

## Cartographie du dépôt (monorepo)

```
python/         Back V2 : métier, orchestrateur Hermes, API HTTP, persistance SQLite
frontend/       Front V2 : dashboard React/Vite (runs, offres scorées, lettres, décisions)
docs/           Vision, definition of done, décisions d'architecture (ADR)
scripts/        Scripts utilitaires (dont la recette E9)
handoffs/       Passations de contexte entre sessions
src/ index.js   V1 Node.js (historique — voir « Legacy V1 » plus bas)
```

Chaque brique V2 a son propre README détaillé :

- **Back** → [`python/README.md`](python/README.md)
- **Front** → [`frontend/README.md`](frontend/README.md)

## Architecture V2 (vue d'ensemble)

```
  ┌────────────┐   HTTP  /api   ┌──────────────┐        ┌───────────────┐
  │  frontend/ │ ─────────────▶ │  API Python  │ ─────▶ │ Hermes +      │
  │ React/Vite │  Bearer token  │ (python/api) │        │ métier + LLM  │
  └────────────┘                └──────────────┘        └───────┬───────┘
                                        │                        │
                                        ▼                        ▼
                                  GET /me, /runs            SQLite (run_store)
```

- L'API expose la consultation (`GET /me`, `GET /runs`, détail, recommandations paginées,
  catalogue d'offres scoré `GET /offers`) et les actions (décision, lettre de motivation,
  `/confirm`) — ces dernières exigent le rôle `reviewer` et une confirmation explicite.
- Le frontend consomme l'API via un proxy `/api` (cf. [`frontend/README.md`](frontend/README.md)) :
  consultation (runs, recommandations, catalogue d'offres) **et** actions validées —
  décision humaine, génération/édition/suppression de lettre, ajout d'offre.
- Auth : jeton porteur validé par `GET /me`, persisté côté client — voir
  [`docs/adr/0002-auth-frontend-localstorage-me.md`](docs/adr/0002-auth-frontend-localstorage-me.md).

## Prérequis

- **Python ≥ 3.11** (back) et **Node.js ≥ 18** (front), ou **Docker** (chemin recommandé,
  reproductible — notamment sous WSL2).

## Démarrage (V2)

### Back — API Python

L'API **refuse de démarrer sans jeton** (`OPPORTUNE_API_TOKEN`). Depuis `python/` :

```bash
export OPPORTUNE_API_TOKEN=mon-jeton          # requis
export OPPORTUNE_API_CANDIDATES=cand-marie    # périmètre : candidats possédés (CSV)
export OPPORTUNE_DB_PATH=data/opportune.db     # base SQLite (défaut : data/opportune.db)
# export OPPORTUNE_API_TOKEN_TTL=3600          # optionnel : expiration du jeton (secondes)

python -m api.server                           # écoute sur http://127.0.0.1:8000
```

### Front — dashboard React

Depuis `frontend/` (l'API doit tourner en parallèle) :

```bash
npm install
npm run dev        # http://localhost:5173, proxy /api → http://localhost:8000
```

Cible du proxy surchargeable via `API_PROXY_TARGET` (ex. réseau Docker).

### Démo Docker de bout en bout

Front et API sur un réseau bridge partagé, ports publiés vers l'hôte (host-networking
inopérant sous Docker Desktop/WSL2). La recette ci-dessous s'appuie sur cette démo.

## Recette

Recette de bout en bout de l'Epic E9 (login → `/me`, liste, pagination, détail,
recommandations, erreurs 401/404, accès direct par ID) :

```bash
bash scripts/recette-e9.sh
# ou en ciblant directement l'API :
BASE=http://localhost:8000 TOKEN=mon-jeton bash scripts/recette-e9.sh
```

## Tests

- **Back** : `cd python && docker compose run --rm app pytest -q`
- **Front** : `cd frontend && docker run --rm -v "$PWD":/app -v /app/node_modules opportune-frontend:dev npm test`

Détails et variantes (venv local, lint, build) dans les READMEs respectifs.

## Configuration

Les variables sensibles se placent dans un `.env.local` (gitignoré, jamais commité).
Voir `.env.example` et les READMEs de chaque brique pour la liste complète.

## Documentation

- [`docs/vision.md`](docs/vision.md) — vision produit
- [`docs/definition-of-done.md`](docs/definition-of-done.md) — definition of done
- [`docs/adr/`](docs/adr/) — décisions d'architecture (ADR)

## Legacy V1 (Node.js)

Le MVP CLI d'origine reste exécutable depuis la racine (récupère les tickets Notion et
suggère le prochain à traiter). Il n'est plus la cible produit ; la logique métier migre
vers `python/`.

```bash
npm install
cp .env.example .env.local   # renseigner NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_DATA_SOURCE_ID…
npm start                    # affiche le prochain ticket recommandé
npm test                     # suite V1 via node --test
```

Les données locales V1 sont stockées en JSON sous `data/` (gitignoré) et ne quittent pas
votre machine.
