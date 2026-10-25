<!-- init-ai-workspace:begin -->
## Workflow IA — Contexte projet

- **Stack détectée :** monorepo — back Python (bibliothèque standard, `python/`) + front React/Vite/TypeScript (`frontend/`)
- **Commande de test :** back `cd python && docker compose run --rm app pytest -q` · front `cd frontend && npm test`
- **Script de contexte :** `scripts/generate-ai-context.sh`
- **Fichier de contexte :** `.claude/skills/project-context.md`

**Règle de fraîcheur :** si `.claude/skills/project-context.md` est absent ou date de plus de 24h, exécute `bash scripts/generate-ai-context.sh` avant toute autre action.

Ce fichier est un point de départ minimal — destiné à être enrichi au fil du temps avec les règles spécifiques au projet (typage, architecture, tests, etc.), en dehors de cette zone gérée par le skill.
<!-- init-ai-workspace:end -->

## Projet Opportune — repères

Assistant de candidature **local-first et mono-utilisateur** (tourne sur la machine de
l'utilisateur, API sur `localhost`, sans login ni jeton — cf. `docs/adr/0003`).

- **Back** (`python/`) : cœur métier + orchestrateur **Hermes** + API HTTP, écrits avec la
  **bibliothèque standard** (zéro dépendance de prod ; extras `scrape`/`discord` confinés).
  Trois couches `app/` (métier) · `hermes/` (orchestration) · `api/` (HTTP). Détail :
  [`python/README.md`](python/README.md).
- **Front** (`frontend/`) : dashboard React 19 + Vite + TypeScript + Tailwind v4 + TanStack
  Query. Détail : [`frontend/README.md`](frontend/README.md).
- **V1 Node.js** (archivée sous `legacy/`) : MVP CLI historique, conservé pour
  référence — plus la cible produit.

**Tests** — back : `cd python && docker compose run --rm app pytest -q` (ou
`python/.venv/bin/pytest`) ; front : `cd frontend && npm test` (Vitest), `npm run lint`
(typecheck `tsc`), `npm run build`.

**Conventions** : voir [`docs/definition-of-done.md`](docs/definition-of-done.md) — une
responsabilité par fichier, logique métier pure et testable sans LLM/réseau, commentaires en
français, secrets hors dépôt (`.env.local`). Vision produit : [`docs/vision.md`](docs/vision.md).
