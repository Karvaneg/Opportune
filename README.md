# Opportune

[![CI](https://github.com/Karvaneg/Opportune/actions/workflows/ci.yml/badge.svg)](https://github.com/Karvaneg/Opportune/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<p align="center">
  <img src="docs/images/Opportune.png" width="320" alt="Opportune — Saisir l'occasion au vol." />
</p>

<p align="center">
  <a href="https://github.com/Karvaneg/Opportune/releases/latest">
    <img src="https://img.shields.io/github/v/release/Karvaneg/Opportune?label=T%C3%A9l%C3%A9charger%20Opportune&style=for-the-badge&color=2ea44f" alt="Télécharger Opportune (Windows, Linux)" />
  </a>
  <br />
  <sub>Windows (<code>.exe</code>, <code>.msi</code>) · Linux (<code>.deb</code>, <code>.rpm</code>, <code>.AppImage</code>) · <a href="#installation">Comment installer</a></sub>
</p>

> **Local-first job-application assistant** — collects job offers, scores them against your
> profile with a local LLM (Ollama), and drafts tailored cover letters. Everything runs on
> your machine, nothing leaves it, and every outbound action needs your explicit approval.

**Highlights**

- 🔒 **Local-first & private** — SQLite storage and a local LLM; no third-party data sharing.
- 🤖 **AI scoring & cover letters** — offer matching and letter drafting powered by Ollama.
- ✋ **Human-in-the-loop** — explicit human validation before any outbound action.
- 🧩 **Clean monorepo** — Python engine + HTTP API (`python/`), React/Vite dashboard (`frontend/`).
- ✅ **Tested & CI-checked** — pytest + Vitest run on every pull request.

> 📖 The documentation below is in French. If you don't read French, the Highlights above
> summarise the project; the architecture diagram and the per-module READMEs are the quickest
> way in.

---

## Installation

Opportune s'installe **par double-clic, sans terminal**, avec son assistant IA local embarqué.

1. Ouvre la page **[Télécharger Opportune](https://github.com/Karvaneg/Opportune/releases/latest)**
   (dernière version publiée) et, dans la partie **Assets**, prends le fichier de ton système :

   | Système | Fichier à télécharger |
   |---|---|
   | Windows | `.exe` (installeur classique) ou `.msi` |
   | Linux (Debian, Ubuntu…) | `.deb` |
   | Linux (Fedora, openSUSE…) | `.rpm` |
   | Linux (toute distribution) | `.AppImage` (rendre exécutable, puis double-clic) |

2. Lance l'installeur. Les installeurs ne sont **pas encore signés** : Windows peut afficher
   « Windows a protégé votre ordinateur » ; clique sur **Informations complémentaires** puis
   **Exécuter quand même**.
3. Au premier lancement, Opportune propose de télécharger le modèle d'IA local (une seule
   fois). Tout reste ensuite sur ta machine.

Mac n'est pas encore disponible. Pour lancer Opportune depuis les sources (développeurs), voir
[Démarrage depuis les sources](#démarrage-depuis-les-sources).

## Sommaire

- [Installation](#installation)
- [Du prototype Node.js à Opportune](#du-prototype-nodejs-à-opportune)
- [Cartographie du dépôt](#cartographie-du-dépôt-monorepo)
- [Architecture](#architecture-vue-densemble)
- [Aperçu et design](#aperçu-et-design)
- [Prérequis](#prérequis)
- [Démarrage depuis les sources](#démarrage-depuis-les-sources)
- [Application de bureau](#application-de-bureau-tauri)
- [Sources d'offres](#sources-doffres--pourquoi-adzuna-par-défaut)
- [Tests](#tests)
- [Configuration](#configuration)
- [Feuille de route](#feuille-de-route)
- [Documentation](#documentation)
- [Prototype Node.js (archivé)](#prototype-nodejs-archivé)

## Du prototype Node.js à Opportune

- **Opportune (Python + React), active.** Le moteur métier, l'orchestrateur **Hermes**, l'API
  HTTP, un **frontend web** (React/Vite) et l'**app de bureau** (Tauri). C'est là que se fait
  le développement courant, et c'est ce que contient la release `v1.0.0`. Code sous `python/`
  et `frontend/`.
- **Prototype Node.js, archivé.** Le MVP en ligne de commande d'origine (intégration Notion,
  stockage JSON) est archivé sous [`legacy/`](legacy/). Conservé comme référence ; il n'est
  plus la cible produit.

**Pourquoi ce pivot ?** Node a permis de **valider vite** la boucle produit ; Python porte
mieux le cœur réel d'Opportune (LLM local, extraction de CV, scoring) et prépare le
**packaging desktop**. Le MVP a fait son travail — prouver la valeur — avant d'investir dans
l'architecture actuelle. Détail : [`docs/adr/0004-pivot-node-python.md`](docs/adr/0004-pivot-node-python.md).

## Cartographie du dépôt (monorepo)

```
python/         Back : métier, orchestrateur Hermes, API HTTP, persistance SQLite
  packaging/    Binaire autonome de l'API (PyInstaller), qui sert aussi le front compilé
frontend/       Front : dashboard React/Vite (runs, offres scorées, lettres, décisions)
  src-tauri/    Coquille de l'app de bureau (Tauri) : lance l'API et Ollama, ouvre la fenêtre
docs/           Vision, definition of done, décisions d'architecture (ADR)
scripts/        Scripts utilitaires (serveur API, contexte IA)
legacy/         Prototype Node.js archivé (MVP CLI, voir plus bas)
```

Chaque brique a son propre README détaillé :

- **Back** → [`python/README.md`](python/README.md)
- **Front** → [`frontend/README.md`](frontend/README.md)
- **App de bureau** → [`frontend/src-tauri/README.md`](frontend/src-tauri/README.md)

## Architecture (vue d'ensemble)

```
  ┌────────────┐   HTTP  /api   ┌──────────────┐        ┌───────────────┐
  │  frontend/ │ ─────────────▶ │  API Python  │ ─────▶ │ Hermes +      │
  │ React/Vite │  même machine  │ (python/api) │        │ métier + LLM  │
  └────────────┘                └──────────────┘        └───────┬───────┘
                                        │                        │
                                        ▼                        ▼
                                  GET /me, /runs            SQLite (run_store)
```

En développement, Vite sert le front et relaie `/api` vers l'API. Dans l'app de bureau, il
n'y a plus de Vite : le binaire API sert lui-même le front compilé sur `127.0.0.1:8000`, et
la coquille Tauri lance ce binaire et Ollama puis ouvre une fenêtre dessus.

- L'API expose la consultation (`GET /me`, `GET /runs`, détail, recommandations paginées,
  catalogue d'offres scoré `GET /offers`) et les actions (décision, lettre de motivation,
  `/confirm`) — ces dernières exigent le rôle `reviewer` et une confirmation explicite.
- Le frontend consomme l'API via un proxy `/api` (cf. [`frontend/README.md`](frontend/README.md)) :
  consultation (runs, recommandations, catalogue d'offres) **et** actions validées :
  décision humaine, génération/édition/suppression de lettre, ajout d'offre, collecte,
  suivi post-candidature, réglages (clés Adzuna, flux RSS) et installation du modèle LLM.
- Auth : **aucune** — local-first et mono-utilisateur (OPP-181). L'API n'écoute que sur
  `localhost` et démarre sans jeton ; au lancement, le frontend fait un simple `GET /me` pour
  identifier l'unique utilisateur local (plus de login ni de jeton porteur). Historique de cette
  décision : [`docs/adr/0003-auth-local-first-sans-jeton.md`](docs/adr/0003-auth-local-first-sans-jeton.md)
  (remplace l'ADR 0002).

## Aperçu et design

Opportune se veut un **copilote de confiance** : sérieux et rigoureux, mais chaleureux — pas un
outil corporate. Sa signature reprend le mythe du **toupet de Kairos** (le dieu grec du moment
opportun, qu'on attrape au passage par son unique mèche de cheveux) : dans le logo, le trait du
**O** se décolle et s'enroule au-dessus des « pp », en indigo. L'occasion passe, Opportune aide à
la saisir.

Interface **React/Vite**, **thèmes clair et sombre** (bascule auto / clair / sombre), couleurs
pilotées par des **jetons sémantiques**. Design system complet :
[`frontend/src/styles/README.md`](frontend/src/styles/README.md).

| Jeton | Rôle | Clair | Sombre |
|---|---|---|---|
| `brand` | marque — mèche, liens, action principale | `#4f46e5` | `#818cf8` |
| `ink` | texte | `#0f172a` | `#f8fafc` |
| `surface` | fond | `#f8fafc` | `#0f172a` |
| `success` | succès | `#059669` | `#34d399` |
| `warning` | alerte | `#d97706` | `#fbbf24` |
| `danger` | erreur | `#dc2626` | `#f87171` |

### Captures d'écran

*Captures prises dans l'espace Démo (aucune donnée personnelle).*

| Écran d'accueil — Démo / Mon espace | Cockpit — guide de démarrage |
|:---:|:---:|
| ![Écran d'accueil Démo / Mon espace](docs/images/WelcomeScreen.png) | ![Cockpit avec le guide « Nouveau profil » en 3 étapes](docs/images/guide.png) |
| **Cockpit — synthèse** | **Profil — CV & compétences** |
| ![Cockpit de synthèse : compteurs et activité récente](docs/images/accueil.png) | ![Profil : import de CV, compétences et parcours](docs/images/profil.png) |
| **Offres scorées** | **Recommandation + lettre** |
| ![Catalogue d'offres scorées](docs/images/offres.png) | ![Fiche recommandation : score, lettre et validation](docs/images/recommandation.png) |

## Prérequis

- **Python ≥ 3.11** (back) et **Node.js ≥ 18** (front).
- **Docker** (facultatif) : un environnement conteneurisé existe toujours, mais ce n'est plus
  la voie utilisée par défaut.

## Démarrage depuis les sources

### Back — API Python

Opportune est **local et mono-utilisateur** : l'API démarre **sans jeton** (local-first,
OPP-181) et n'écoute que sur `localhost`.

**Démarrage simplifié (recommandé, OPP-153)** — depuis la racine du dépôt :

```bash
bash scripts/serve-api.sh                      # écoute sur http://127.0.0.1:8000
```

Le script lit toute la configuration depuis `python/.env` (**source unique** — plus de
variables à retaper), **auto-détecte `OLLAMA_HOST`** sous WSL et utilise le venv s'il existe
(modèle : [`python/.env.example`](python/.env.example)). La première **recherche** se crée
ensuite directement **depuis l'app** (barre de recherche). Détails :
[`python/README.md`](python/README.md#lancer-lapi).

**Démarrage manuel** (variables à l'ancienne) — depuis `python/` :

```bash
export OPPORTUNE_DB_PATH=data/opportune.db     # base SQLite (défaut : data/opportune.db)

python -m api.server                           # écoute sur http://127.0.0.1:8000
```

### Front — dashboard React

Depuis `frontend/` (l'API doit tourner en parallèle) :

```bash
npm install
npm run dev        # http://localhost:5173, proxy /api → http://localhost:8000
```

Cible du proxy surchargeable via `API_PROXY_TARGET`.

## Application de bureau (Tauri)

Pour construire l'app de bureau et ses installeurs (Linux depuis WSL ou Linux, Windows depuis
l'hôte Windows) : [`frontend/src-tauri/README.md`](frontend/src-tauri/README.md). L'app lance
l'API et un Ollama embarqué (version CPU), propose de télécharger le modèle au premier
lancement, et range bases SQLite et modèles dans un seul dossier de données propre à l'app.

## Sources d'offres — pourquoi Adzuna par défaut

Opportune collecte des offres réelles via des **connecteurs** (détail et commandes :
[`python/README.md`](python/README.md#collecter-des-offres-réelles-opp-120--opp-122)) :

- **Adzuna** — source **recommandée et par défaut** : inscription gratuite et **clé délivrée
  instantanément en self-service**, idéale pour que n'importe qui installe Opportune et collecte
  tout de suite (quota gratuit ~2 500 appels/mois). La clé se saisit dans la page **Réglages**
  de l'app.
- **RSS/Atom** — sans identifiant, à alimenter avec vos propres flux d'alertes emploi
  (URLs saisies dans les **Réglages**).
- **Entreprises ciblées** — sans identifiant : vous collez dans les **Réglages** la page carrière
  des entreprises qui vous intéressent, si elles publient via Greenhouse ou Lever. Opportune lit
  leurs offres en France directement à la source.
- **France Travail** — l'API officielle, la plus riche, mais **indisponible aujourd'hui**
  (vérifié oct. 2026) : elle a été **retirée de `francetravail.io`** le temps d'une analyse des
  modalités de distribution/réutilisation, suite à des **usages automatisés massifs par des
  solutions d'IA**. À sa réouverture, l'accès sera **sur autorisation préalable** (pas de
  self-service), ce qui se prête mal à une diffusion large. Le connecteur existe mais reste
  **dormant** — d'où le choix d'Adzuna comme source par défaut.

## Tests

- **Back** : `cd python && .venv/bin/pytest -q`
- **Front** : `cd frontend && npm test`

Détails et variantes (lint, build, Docker en option) dans les READMEs respectifs.

## Configuration

Dans l'app, la configuration utile (clés Adzuna, flux RSS, installation du modèle) se fait
depuis l'interface, sans fichier à éditer. Pour le développement, la config du back se trouve
dans `python/.env` (modèle : [`python/.env.example`](python/.env.example)), lu par
`scripts/serve-api.sh` ; ce fichier est gitignoré et ne doit jamais être commité. Le
`.env.example` à la racine (modèle du `.env.local`, lui aussi gitignoré) ne concerne que les
skills de workflow `/start-ticket` et `/ship`.

## Feuille de route

**Opportune 1.0 — installation grand public.** Objectif : rendre Opportune installable par
**n'importe quelle personne en recherche d'emploi**, sans compétences techniques.

Déjà en place (branche d'intégration `epic/E13-opportune-1.0`) :

- 📦 **Application de bureau Tauri** : le moteur Python (binaire PyInstaller) et le dashboard
  sont embarqués ; installeurs **Linux** (`.deb`, `.rpm`, `.AppImage`) et **Windows**
  (`.msi`, `.exe`) construits depuis les sources.
- 🧠 **LLM clé en main** : l'app lance un **Ollama embarqué** et télécharge le modèle au premier
  lancement, depuis l'interface. Le **tout-local** est préservé.
- ⚙️ **Configuration dans l'app** : clés Adzuna et flux RSS dans la page Réglages, plus de
  `.env` à éditer ; l'espace Démo est utilisable tout de suite.

Reste à faire :

- Publier une première version téléchargeable.
- **Signer** les installeurs Windows (avertissement SmartScreen, OPP-217).
- Installeur **Mac** signé et notarisé (OPP-216).
- Plus tard : remplacer Ollama par un moteur **llama.cpp** embarqué (OPP-196), et un **LLM
  cloud optionnel** pour les machines modestes (OPP-197).

En attendant une version publiée, l'installation décrite plus haut (environnement
Python/Node ou Docker) reste la voie pour les profils techniques et les contributeurs.

## Documentation

- [`docs/vision.md`](docs/vision.md) — vision produit
- [`docs/definition-of-done.md`](docs/definition-of-done.md) — definition of done
- [`docs/adr/`](docs/adr/) — décisions d'architecture (ADR)
- [`frontend/src-tauri/README.md`](frontend/src-tauri/README.md) — app de bureau et installeurs
- [`python/docs/`](python/docs/) — collecte d'offres, revue Discord (historique)

## Prototype Node.js (archivé)

Le MVP CLI d'origine est archivé sous [`legacy/`](legacy/) (récupère les tickets Notion et
suggère le prochain à traiter). Il n'est plus la cible produit ; la logique métier a migré
vers `python/`. Il reste exécutable depuis son dossier :

```bash
cd legacy
npm install
cp .env.example .env.local   # renseigner NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_DATA_SOURCE_ID…
npm start                    # affiche le prochain ticket recommandé
npm test                     # suite du prototype via node --test
```

Détails dans [`legacy/README.md`](legacy/README.md). Les données locales du prototype sont stockées
en JSON sous `data/` (gitignoré) et ne quittent pas votre machine.
