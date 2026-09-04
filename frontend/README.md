# Opportune — Frontend (Hermes)

Dashboard interne de consultation des runs Hermes. Consomme l'API Python
(`python/src/api`). Stack : React 19 + TypeScript + Vite, Tailwind v4, TanStack Query,
React Router, Vitest + Testing Library.

## Périmètre (OPP-100)

- Page `/runs/:runId` : métadonnées du run, évaluations, erreurs, et recommandations
  paginées (lecture seule).
- Auth MVP : jeton saisi dans l'UI → `authStorage` (localStorage) → `Authorization: Bearer`.
  Déconnexion explicite + purge automatique du jeton sur `401`.
- Le listing des runs (`GET /runs`) est **hors périmètre** → OPP-101.
- Le durcissement de l'auth (session) → OPP-102.

## Développement

```bash
npm install
npm run dev        # Vite sur http://localhost:5173, proxy /api → http://localhost:8000
```

L'API Python doit tourner en parallèle (`cd ../python && python -m api.server`).
Les appels front sont préfixés `/api` et réécrits vers l'API par le proxy Vite.

## Qualité

```bash
npm run lint       # tsc -b (typecheck strict)
npm test           # Vitest (client API + composants)
npm run build      # typecheck + build de production
```

## Docker

```bash
docker build -t opportune-frontend:dev .
docker run --rm opportune-frontend:dev npm test   # exécuter la suite
docker run --rm -p 5173:5173 opportune-frontend:dev   # serveur de dev
```

## Conventions

- Le frontend ne déduit **aucune** information métier absente du contrat API
  (`src/api/types.ts`, fidèle à `python/src/api/app.py`).
- Messages d'erreur neutres : un `404` ne distingue jamais « inexistant » de
  « hors périmètre » (anti-énumération, cohérent avec OPP-097).
