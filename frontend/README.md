# Opportune — Frontend (Hermes)

Dashboard interne Hermes : consultation des runs **et** actions de candidature validées
(décision, lettre de motivation, ajout d'offre). Consomme l'API Python (`python/src/api`).
Stack : React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, React Router,
Vitest + Testing Library.

## Périmètre

- **Login** (`LoginGate`) : jeton saisi dans l'UI → session (`authStorage`, localStorage) →
  `Authorization: Bearer` ; déconnexion explicite + purge automatique du jeton sur `401` (OPP-102).
- **Runs** : liste paginée (`/`) et détail d'un run (`/runs/:runId`) — métadonnées,
  évaluations, erreurs, recommandations paginées.
- **Catalogue d'offres** (`/offres`) : tout le stock, annoté du **score de match** (calcul
  par règles, sans IA) pour le candidat sélectionné ; ajout d'une offre par texte collé ou URL.
- **Recommandation** (`/recommendations/:id`) : détail, **panneau lettre** de motivation
  (générer / éditer / supprimer) et **décision** humaine (réservée au rôle `reviewer`).

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
