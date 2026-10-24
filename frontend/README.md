# Opportune — Frontend (Hermes)

Dashboard local Hermes : consultation des runs **et** actions de candidature validées
(décision, lettre de motivation, ajout d'offre). Consomme l'API Python (`python/src/api`).
Stack : React 19 + TypeScript + Vite, Tailwind v4, TanStack Query, React Router,
Vitest + Testing Library.

## Périmètre

- **Amorçage local** (`AuthContext`, OPP-181) : app locale **sans login ni jeton** ; au
  démarrage un `GET /me` identifie l'unique utilisateur local, ou affiche « API injoignable »
  (+ « Réessayer ») si le serveur n'est pas lancé.
- **Écran d'accueil « Démo / Mon espace »** (`src/space/`, OPP-182) : avant d'entrer, on
  choisit un **espace** — « Mon espace » (vraies données) ou « Démo » (exemple isolé). Le back
  sert deux bases SQLite distinctes selon l'en-tête `X-Opportune-Space` ; en démo, un bandeau
  (`DemoBanner`) permet de repartir de zéro ou de restaurer l'exemple.
- **Sélecteur de recherche** (`SearchBar`, OPP-184) : barre globale pour **basculer, créer ou
  renommer** la recherche active (le périmètre « recherche » au sens produit).
- **Cockpit** (`/`) : accueil de synthèse — compteurs, raccourcis, flux d'activité récente,
  guide « nouveau profil » (OPP-164/165/177).
- **Catalogue d'offres** (`/offres`) : tout le stock, annoté du **score de match** (calcul
  par règles, sans IA) pour la recherche active ; ajout d'une offre par texte collé ou URL
  (`AddOffer`) et collecte de nouvelles offres (`CollectOffers`).
- **Profil** (`/profil`) : profil candidat de la recherche, avec import de CV (PDF).
- **Historique** (`/historique`) : liste paginée des runs, et détail d'un run
  (`/runs/:runId`) — métadonnées, évaluations, erreurs, recommandations paginées.
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
