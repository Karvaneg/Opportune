# Opportune — back Python

Cœur métier d'Opportune : analyse d'offres, scoring, recommandation, décisions
et actions sensibles, orchestrés par **Hermes** et exposés via une **API HTTP**. C'est la
stack cible du projet (le prototype Node.js, archivé sous [`../legacy/`](../legacy/), est historique
— voir le README racine).

**Zéro dépendance de production** : tout le métier, l'orchestrateur et l'API sont écrits
avec la **bibliothèque standard** (`sqlite3`, `urllib`, `http.server`). Seul `pytest` est
requis, et seulement pour les tests. Les fonctions optionnelles vivent dans des extras
confinés : `pdf` (pypdf, import de CV), `scrape` (BeautifulSoup, intake par URL et RSS),
`discord` (récepteur de clics historique) et `build` (PyInstaller, binaire autonome).

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

Côté interface, « recherche » (vocabulaire produit, OPP-184) ; côté API/technique, le
périmètre reste porté par l'identifiant historique `candidate_id` (routes `/candidates/...`,
inchangées par décision).

| Méthode & route | Rôle |
|---|---|
| `GET /me` | Sonde d'amorçage + identité locale (`{id, role, owned_count}`) |
| `GET /searches` | Liste les recherches de l'espace (OPP-184) |
| `POST /searches` | Crée une recherche nommée (rôle `reviewer`) |
| `PUT /searches/{search_id}` | Renomme une recherche (rôle `reviewer`) |
| `GET /runs` | Listing paginé des runs du périmètre |
| `GET /runs/{run_id}` | Détail d'un run (évaluations, erreurs) |
| `DELETE /runs/{run_id}` | Supprime un run de l'historique |
| `GET /runs/{run_id}/recommendations` | Recommandations paginées + filtres `advisory_status`/`decision_status` |
| `POST /candidates/{candidate_id}/recommendations` | Lance une recommandation |
| `GET /candidates/{candidate_id}/stats` | Agrégats de décision du périmètre (OPP-163) |
| `GET /candidates/{candidate_id}/activity` | Flux d'activité récente — lettres, décisions, ajouts (OPP-165) |
| `GET /candidates/{candidate_id}/scoring-quality` | Scores des offres retenues contre rejetées, conclusion à partir de 10 de chaque (OPP-234) |
| `GET /candidates/{candidate_id}/profile` | Lecture du profil candidat |
| `PUT /candidates/{candidate_id}/profile` | Création / mise à jour du profil |
| `POST /candidates/{candidate_id}/profile/cv` | Import d'un CV PDF → extraction + profil (OPP-174, LLM) |
| `POST /candidates/{candidate_id}/offers/{offer_id}/rescore` | Recalcule le score d'une offre |
| `GET /recommendations/{recommendation_id}` | Détail d'une recommandation |
| `POST /recommendations/{recommendation_id}/decision` | Validation humaine (rôle `reviewer`) |
| `GET /recommendations/{recommendation_id}/letter` | Lettre de motivation courante (si générée) |
| `POST /recommendations/{recommendation_id}/letter` | Génère la lettre (LLM, rôle `reviewer`) |
| `PUT /recommendations/{recommendation_id}/letter` | Édite la lettre (rôle `reviewer`) |
| `DELETE /recommendations/{recommendation_id}/letter` | Supprime la lettre (rôle `reviewer`) |
| `GET /offers` | Catalogue du pool d'offres, annoté du score de match |
| `POST /offers` | Intake d'une offre par texte collé (OPP-145) ou URL (OPP-148) |
| `GET /collect` | État du job de collecte actif, s'il y en a un (OPP-208) |
| `POST /collect` | Lance une collecte asynchrone, source `adzuna` (`what` requis), `rss` ou `ats` (job de fond, OPP-170) |
| `GET /collect/{job_id}` | Sonde la progression d'un job de collecte |
| `POST /collect/{job_id}/cancel` | Annule un job de collecte en cours |
| `GET /system/llm/status` | État du LLM local : Ollama joignable, modèle présent (OPP-193) |
| `GET /system/llm/setup` | Avancement du téléchargement du modèle |
| `POST /system/llm/setup` | Lance le téléchargement du modèle (202) |
| `GET /settings/adzuna` | Clés Adzuna configurées ou non (jamais les clés elles-mêmes, OPP-222) |
| `PUT /settings/adzuna` | Enregistre les clés Adzuna saisies dans l'app |
| `GET /settings/rss` | URLs de flux RSS enregistrées (OPP-195) |
| `PUT /settings/rss` | Remplace la liste des flux RSS (liste vide = tout supprimer, OPP-225) |
| `GET /settings/follow-up` | Délais de relance, en jours (OPP-235) |
| `PUT /settings/follow-up` | Remplace les délais de relance après une candidature et après un entretien (OPP-235) |
| `GET /settings/ats` | Entreprises ciblées enregistrées (pages carrière Greenhouse/Lever, OPP-226) |
| `PUT /settings/ats` | Vérifie auprès de l'ATS puis enregistre les entreprises (liste vide = tout supprimer) |
| `POST /data/export` | Rend l'archive `.zip` de l'espace (base + réglages, clés Adzuna comprises) en base64 (`archive_base64`) avec un nom daté (`filename`) ; le front l'enregistre où l'utilisateur choisit (OPP-232) |
| `POST /data/import` | Remplace la base et les réglages par une archive (`archive_base64`) ; 400 si l'archive est invalide ou vient d'une version plus récente, 409 pendant une collecte |
| `POST /applications/{recommendation_id}/confirm` | Action sensible : candidature (confirmation explicite + décision `approved` + rôle `reviewer`) |
| `POST /applications/{recommendation_id}/applied` | Suivi : « j'ai candidaté » (date optionnelle) |
| `DELETE /applications/{recommendation_id}/applied` | Annule la candidature déclarée |
| `GET /applications/{recommendation_id}/tracking` | Historique de suivi post-candidature (OPP-223) |
| `POST /applications/{recommendation_id}/tracking` | Ajoute un événement : entretien daté, rejet, offre reçue |
| `POST /messages/{contact_id}/confirm` | Action sensible : message (mêmes gardes) |
| `POST /demo/reset` · `POST /demo/restore` | Vide / restaure l'espace Démo (cf. « Deux espaces isolés ») |

Certaines routes ne sont **montées que si leur service est câblé** (recherches, profil, CV,
lettre, intake `POST /offers`, `/collect`, `/system/llm/*`, `/settings/*`, actions sensibles,
suivi) ; sinon elles répondent **404 neutre**.

Côté transport (`server.py`), les routes de l'API sont préfixées **`/api`** ; toute autre
requête `GET` sert le **front compilé** (`frontend/dist`, OPP-191) quand il est présent, ce qui
permet au binaire autonome de livrer front et API sur le même origin.

Gardes de sécurité (OPP-181, local-first) : l'API est **mono-utilisateur sur `localhost` et
sans jeton** — toute requête est servie comme l'unique utilisateur local (pas de 401 en
fonctionnement normal ; un filet 401 subsiste si un fournisseur d'auth strict était câblé).
Restent la **propriété** de la ressource (sinon **404**) et, pour les actions réservées, le
**rôle `reviewer`** (**403**). Les 404 sont **neutres** : « inexistant » et « hors périmètre »
sont indistinguables (anti-énumération).

Contrôle de l'en-tête `Origin` (OPP-233, `api/origin_guard.py`) : une écriture (`POST`, `PUT`,
`DELETE`) envoyée par la page d'un autre site reçoit un **403** avant tout dispatch. Sont
acceptées l'origine de l'API (`127.0.0.1`, `localhost` ou `[::1]` sur le port d'écoute), les
requêtes **sans** `Origin` (curl, tests, scripts) et, **hors app packagée**, le front de dev
(`:5173` pour `npm run dev`, `:4173` pour `npm run preview`). Un front ouvert depuis une autre
adresse (`npm run dev -- --host` ouvert par l'IP WSL, par exemple) s'autorise via
`OPPORTUNE_EXTRA_ORIGINS` (origines séparées par des virgules, ex.
`OPPORTUNE_EXTRA_ORIGINS=http://172.18.0.5:5173`).

Contrôle de l'en-tête `Host` (OPP-233, `api/host_guard.py`, contre le DNS rebinding) : toute
requête, lecture comprise, dont le `Host` n'est pas `127.0.0.1`, `localhost` ou `[::1]` sur le
port d'écoute reçoit un **403**. Le proxy Vite réécrit `Host` vers sa cible (`changeOrigin`) :
une cible `API_PROXY_TARGET` qui n'est pas un nom local sera donc refusée.

## Prérequis

- **Python ≥ 3.11**. Docker reste possible en option (cf. [Environnement Docker](#environnement-docker-optionnel)),
  mais ce n'est plus la voie utilisée par défaut.

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
.venv/bin/pytest -q            # ou `pytest` si le venv est activé
```

La suite couvre chaque brique métier, l'orchestrateur et l'API (services, pagination,
filtres, auth, décisions, actions), sans réseau : LLM injecté et dépôts SQLite en mémoire.

## Lancer l'API

Opportune est **local et mono-utilisateur** : l'API démarre **sans jeton** (local-first,
OPP-181). Elle n'écoute que sur `localhost`, pour une seule personne sur sa machine.

### Démarrage simplifié (recommandé, OPP-153)

```bash
bash scripts/serve-api.sh      # depuis la racine du dépôt
```

Le script lit toute la configuration depuis `python/.env` (**source unique** — plus de
variables à retaper à chaque lancement), **auto-détecte `OLLAMA_HOST`** sous WSL (passerelle
de l'adaptateur WSL, dont l'IP peut changer entre reboots) quand il n'est pas fixé, puis
lance `python -m api.server` (venv s'il existe, sinon `python3`). La première **recherche** se
crée ensuite directement **depuis l'app** (barre de recherche) ; modèle de configuration :
[`.env.example`](.env.example).

### Démarrage manuel (variables à l'ancienne)

```bash
cd python
export OPPORTUNE_DB_PATH=data/opportune.db     # base SQLite (défaut : data/opportune.db)

python -m api.server                           # écoute sur http://127.0.0.1:8000
```

Port surchargeable par `OPPORTUNE_API_PORT` (défaut `8000`). Le frontend React (`../frontend`) consomme cette API via un proxy `/api` (cf.
`frontend/README.md`).

### Ajouter une offre (texte collé ou URL)

`POST /offers` accepte **soit** `text` (le texte de l'offre, OPP-145), **soit** `url` (le
back récupère la page et en extrait le texte, OPP-148 — le texte prime si les deux sont
fournis). La collecte par URL extrait le texte via **BeautifulSoup**, confiné dans l'extra
`scrape` (le cœur reste sans dépendance) :

```bash
pip install -e ".[scrape]"     # beautifulsoup4, requis pour l'intake par URL
```

Garde-fous : seules les URL **http(s)** sont acceptées, et toute cible interne
(localhost, IP privées/boucle locale/lien-local) est refusée (protection SSRF — le back
émet une requête sortante vers une URL fournie par l'utilisateur). Les échecs sont
distincts : URL refusée/schéma invalide → 400 ; page injoignable, bloquée (403/429) ou
vide → 502. Le JS côté client et les anti-bots sérieux ne sont pas contournés (fetch HTTP
simple) : certains sites échoueront, c'est attendu.

## Environnement Docker (optionnel)

Conteneur reproductible (OPP-071), toujours fonctionnel mais **plus utilisé par défaut** : le
développement et les tests se font avec le venv local (cf. [Installation](#installation)).
Le code (`src/`, `tests/`) est monté en volume : les
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

- Chemin par défaut : `opportune.db` dans le **dossier de données** (cf. ci-dessous),
  surchargeable par `OPPORTUNE_DB_PATH` (`:memory:` accepté pour les tests).
- Dossier de données (`app.paths.user_data_dir`, OPP-190) : `OPPORTUNE_DATA_DIR` s'il est
  défini ; sinon, en **binaire gelé** (PyInstaller), un dossier par utilisateur selon l'OS
  (`%APPDATA%\Opportune`, `~/Library/Application Support/Opportune`,
  `$XDG_DATA_HOME/opportune` ou `~/.local/share/opportune`) ; sinon `data/` relatif (dev).
  L'app de bureau impose `OPPORTUNE_DATA_DIR` pour ranger bases et modèles ensemble.
- `app.db.connect()` ouvre une connexion configurée (lignes `sqlite3.Row`, clés étrangères
  activées) et crée le dossier parent au besoin.
- Sous Docker Compose, la base est persistée dans le volume `opportune-data`.

```python
from app.db import connect, healthcheck

conn = connect()            # data/opportune.db (ou OPPORTUNE_DB_PATH)
assert healthcheck(conn)    # SELECT 1
conn.close()
```

### Deux espaces isolés — « Mon espace » / « Démo » (OPP-182)

L'API sert **deux bases SQLite séparées** : les vraies données (« Mon espace »,
`OPPORTUNE_DB_PATH`, défaut `data/opportune.db`) et un **exemple isolé** (« Démo »,
`OPPORTUNE_DEMO_DB_PATH`, défaut `data/opportune-demo.db`, semé automatiquement au premier
démarrage). Un `SpaceRouter` (`api.space_router`) aiguille **chaque requête** vers l'espace
porté par l'en-tête HTTP **`X-Opportune-Space`** (`mine` ou `demo`) — **défaut `mine`** : on
ne bascule sur la démo que sur demande explicite du front, jamais par accident. Les deux
bases ne se mélangent jamais.

Le routeur porte aussi deux **commandes réservées à la démo**, interceptées avant le routage :
`POST /demo/reset` (vider l'espace démo) et `POST /demo/restore` (restaurer la vitrine).

La vitrine inclut des **réglages de collecte pré-remplis** (`app.demo_settings`) : deux flux RSS
(We Work Remotely full-stack, Remotive) et deux entreprises ciblées (Swile sur Lever, Mirakl sur
Greenhouse). Ils sont posés au premier lancement et par `POST /demo/restore`, et vidés par
`POST /demo/reset` comme le reste.

## Réglages saisis dans l'app (OPP-195 / OPP-222)

Les **clés Adzuna**, les **URLs de flux RSS** et les **pages carrière des entreprises
ciblées** se saisissent dans la page Réglages du front (`PUT /settings/adzuna`,
`PUT /settings/rss`, `PUT /settings/ats`). L'API les range dans des fichiers du dossier de
données (`app.adzuna_credentials_store`, `app.rss_feeds_store`), hors dépôt. L'API n'utilise
**que** les clés Adzuna saisies dans les Réglages de l'espace (OPP-227) : `ADZUNA_APP_ID` /
`ADZUNA_APP_KEY` de l'environnement ne servent plus qu'aux runners en ligne de commande. L'espace Démo a ses propres fichiers : ses réglages ne fuitent pas dans « Mon
espace ».

## Binaire autonome (PyInstaller, OPP-190 / OPP-191)

`packaging/` construit un exécutable unique qui sert **front compilé + API**, sans Python ni
Node installés. C'est le sidecar embarqué par l'app de bureau
([`../frontend/src-tauri/README.md`](../frontend/src-tauri/README.md)).

```bash
cd python
.venv/bin/pip install -e ".[build,scrape,pdf]"
bash packaging/build-api.sh          # reconstruit le front puis produit dist/opportune-api
```

PyInstaller ne fait pas de cross-compilation : le binaire cible l'OS courant (sous Windows,
passer par `frontend/src-tauri/sync-sidecar.ps1`).

## LLM local — Ollama / Ministral

Accès au modèle via un client minimal (`app.llm` / `app.llm_client`) qui parle l'API HTTP
d'Ollama avec `urllib` — **aucune dépendance**. Le transport est **injectable** : les tests
n'ont besoin d'aucun serveur Ollama.

- `OLLAMA_HOST` (défaut `http://localhost:11434`) et `OLLAMA_MODEL` (défaut `ministral-3:3b`)
  surchargeables par l'environnement.
- `OPPORTUNE_LLM_TIMEOUT` (défaut `300` s) borne chaque appel LLM : un intake réaliste en
  sortie structurée prend ~85 s avec `ministral-3:3b` (le défaut brut de 60 s ne suffit pas).
  `OLLAMA_NUM_PREDICT` (défaut `2048`) plafonne les tokens générés, dimensionné sur la lettre.
- Si l'on passe par Docker Compose (optionnel), l'app joint l'Ollama **natif de l'hôte** via `host.docker.internal:11434`
  (`extra_hosts: host-gateway`).
- Une adresse d'écoute sans port dans `OLLAMA_HOST` (`0.0.0.0`, `::`) est ramenée à
  `127.0.0.1:11434` : c'est la valeur côté serveur Ollama, pas une adresse joignable.
- Dans l'app de bureau, Ollama est **embarqué et lancé** par la coquille Tauri, et le modèle
  se télécharge depuis l'app au premier lancement (`/system/llm/*`, OPP-193).

Prérequis côté hôte : un serveur Ollama en écoute et le modèle déjà présent.

```bash
ollama serve                 # sur l'hôte (Windows/WSL), si pas déjà lancé
ollama pull ministral-3:3b   # télécharge le modèle (une fois)
```

Sous **Windows / WSL2** : travailler depuis le système de fichiers Linux (`~/Opportune`, pas
`/mnt/c/...`) ; pour joindre l'Ollama natif Windows, lancer le serveur avec
`OLLAMA_HOST=0.0.0.0` et autoriser le port `11434` depuis le réseau Hyper-V/WSL dans le
pare-feu Windows.

## Validation humaine — revue Discord (interface historique)

> ⚠️ **Interface historique (MVP).** La validation courante se fait dans le **frontend web**
> (cf. [`../frontend/README.md`](../frontend/README.md)). Le chemin Discord reste **fonctionnel
> et testé** mais n'est plus l'interface de référence.

Un dossier prêt (offre + lettre) peut être **poussé** dans un salon Discord avec trois boutons
Approuver / Rejeter / Différer, routés vers la décision métier
(`POST /recommendations/{id}/decision`). Transport et autorisation sont sans dépendance
(`urllib`, allowlist **fail-closed**) ; le récepteur de clics (`hermes.discord_gateway`) et la
boucle push de bout en bout (`hermes.push_runner`, idempotente) vivent dans l'extra `[discord]`.

→ Détail complet (modules, gateway, boucle push, idempotence, variables) :
[`docs/revue-discord.md`](docs/revue-discord.md) · mise en route pas à pas :
[`docs/runbook-bot-discord.md`](docs/runbook-bot-discord.md).

## Collecter des offres réelles (OPP-120 / OPP-122)

La collecte réelle branche une **source** (port `SourceOffres`) sur le socle (OPP-119) :
dédoublonnage **avant** analyse LLM, normalisation, persistance. Chaque runner lit sa config,
assemble sa source et lance la passe (`app.collection_runner`), avec un bilan (collectées /
persistées / doublons / échecs) ; un échec de la **source** sort en code non nul, les échecs
par offre sont consignés sans interrompre la passe.

| Source | Module | Statut | Identifiants |
|---|---|---|---|
| **Adzuna** (recommandée) | `app.adzuna_runner` | actif | clé gratuite **self-service instantanée** |
| **RSS / Atom** | `app.rss_runner` | actif | aucun (vous fournissez les flux) ; extra `scrape` |
| **Entreprises ciblées** (Greenhouse, Lever) | `app.ats_source` (depuis l'app) | actif | aucun (vous fournissez les pages carrière) |
| **France Travail** | `app.france_travail_runner` | **dormant** | API retirée de `francetravail.io` (oct. 2026) |

**Adzuna** est la source par défaut (clé instantanée). Dans l'app, la collecte se lance depuis
le catalogue d'offres (`POST /collect`) avec les clés et flux saisis dans les Réglages ; les
runners en ligne de commande lisent toujours l'environnement. **France Travail**, plus riche, n'est
**pas utilisable** aujourd'hui (API retirée ; futur accès « Restreint » sur autorisation au cas
par cas, inadapté à une diffusion grand public).

→ Commandes, options et détail par connecteur : [`docs/collecte-offres.md`](docs/collecte-offres.md).
