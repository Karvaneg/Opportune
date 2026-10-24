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
| `GET /runs/{run_id}/recommendations` | Recommandations paginées + filtres `advisory_status`/`decision_status` |
| `POST /candidates/{candidate_id}/recommendations` | Lance une recommandation |
| `GET /candidates/{candidate_id}/stats` | Agrégats de décision du périmètre (OPP-163) |
| `GET /candidates/{candidate_id}/activity` | Flux d'activité récente — lettres, décisions, ajouts (OPP-165) |
| `GET /candidates/{candidate_id}/profile` | Lecture du profil candidat |
| `POST /candidates/{candidate_id}/profile` | Création / mise à jour du profil |
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
| `POST /collect` | Lance une collecte asynchrone (job de fond, OPP-170) |
| `GET /collect/{job_id}` | Sonde la progression d'un job de collecte |
| `POST /applications/{recommendation_id}/confirm` | Action sensible : candidature (confirmation explicite + décision `approved` + rôle `reviewer`) |
| `POST /applications/{recommendation_id}/applied` | Suivi : « j'ai candidaté » (date optionnelle) |
| `DELETE /applications/{recommendation_id}/applied` | Annule la candidature déclarée |
| `POST /messages/{contact_id}/confirm` | Action sensible : message (mêmes gardes) |

Certaines routes ne sont **montées que si leur service est câblé** (profil, lettre, intake
`POST /offers`, `/collect`, actions sensibles) ; sinon elles répondent **404 neutre**.

Gardes de sécurité (OPP-181, local-first) : l'API est **mono-utilisateur sur `localhost` et
sans jeton** — toute requête est servie comme l'unique utilisateur local (pas de 401 en
fonctionnement normal ; un filet 401 subsiste si un fournisseur d'auth strict était câblé).
Restent la **propriété** de la ressource (sinon **404**) et, pour les actions réservées, le
**rôle `reviewer`** (**403**). Les 404 sont **neutres** : « inexistant » et « hors périmètre »
sont indistinguables (anti-énumération).

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

Opportune est **local et mono-utilisateur** : l'API démarre **sans jeton** (local-first,
OPP-181). Elle n'écoute que sur `localhost`, pour une seule personne sur sa machine.

### Démarrage simplifié (recommandé, OPP-153)

```bash
bash scripts/serve-api.sh      # depuis la racine du dépôt
```

Le script lit toute la configuration depuis `python/.env` (**source unique** — plus de
variables à retaper à chaque lancement), **auto-détecte `OLLAMA_HOST`** sous WSL (passerelle
de l'adaptateur WSL, dont l'IP peut changer entre reboots) quand il n'est pas fixé, puis
lance `python -m api.server` (venv s'il existe, sinon `python3`). Renseigner au minimum
`OPPORTUNE_API_CANDIDATES` dans `python/.env` (modèle : [`.env.example`](.env.example)).

### Démarrage manuel (variables à l'ancienne)

```bash
cd python
export OPPORTUNE_API_CANDIDATES=cand-marie    # périmètre : candidats possédés (CSV)
export OPPORTUNE_DB_PATH=data/opportune.db     # base SQLite (défaut : data/opportune.db)

python -m api.server                           # écoute sur http://127.0.0.1:8000
```

Le frontend React (`../frontend`) consomme cette API via un proxy `/api` (cf.
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

## LLM local — Ollama / Ministral

Accès au modèle via un client minimal (`app.llm` / `app.llm_client`) qui parle l'API HTTP
d'Ollama avec `urllib` — **aucune dépendance**. Le transport est **injectable** : les tests
n'ont besoin d'aucun serveur Ollama.

- `OLLAMA_HOST` (défaut `http://localhost:11434`) et `OLLAMA_MODEL` (défaut
  `ministral-3:3b`) sont surchargeables par variables d'environnement.
- `OPPORTUNE_LLM_TIMEOUT` (défaut `300` s) borne tout appel LLM — runner push, intake de
  profil **et** intake d'offre collée (`POST /offers`). Le défaut brut de 60 s ne suffit
  pas : un intake réaliste en sortie structurée prend ~85 s avec `ministral-3:3b`.
  `OLLAMA_NUM_PREDICT` (défaut `2048`) plafonne les tokens générés par appel : un plafond
  anti-emballement dimensionné sur la sortie la plus longue (la lettre), pas sur l'intake —
  sinon une lettre légitime serait tronquée.
- Sous Docker Compose, l'app s'appuie sur l'Ollama **natif de l'hôte** (pas de conteneur
  Ollama) : elle le joint via `host.docker.internal:11434` (`extra_hosts` :
  `host-gateway`), avec le modèle `ministral-3:3b`. Le design conteneurisé (service
  `ollama` + volume `ollama-models`) reste dans l'historique git, à réactiver le jour du
  packaging portable (cf. OPP-113).

Prérequis côté hôte : un serveur Ollama en écoute et le modèle déjà présent.

```bash
ollama serve                 # sur l'hôte (Windows/WSL), si pas déjà lancé
ollama pull ministral-3:3b   # télécharge le modèle (une fois)
```

### Sous Windows / WSL2

- Installer **Docker Desktop** avec le backend **WSL2**, ou le moteur Docker directement
  dans la distribution WSL.
- Travailler depuis le système de fichiers Linux de WSL (par ex. `~/Opportune`) plutôt que
  `/mnt/c/...` : les montages de volumes y sont nettement plus rapides.
- Pour que le conteneur joigne l'Ollama natif Windows, lancer le serveur avec
  `OLLAMA_HOST=0.0.0.0` et autoriser le port `11434` depuis le réseau Hyper-V/WSL dans le
  pare-feu Windows.

## Validation humaine — revue Discord (push-to-triage)

> ⚠️ **Interface historique (MVP).** La validation courante se fait désormais dans le
> **frontend web** (cf. [`frontend/README.md`](../frontend/README.md)). Le chemin Discord
> ci-dessous — ainsi que la boucle push plus bas — reste **fonctionnel et testé**, mais n'est
> plus l'interface de référence ; il est conservé comme option et pour l'historique
> (cf. `docs/vision.md`).

Quand un dossier est prêt (offre + lettre générée), il est **poussé** dans un salon
Discord avec trois boutons Approuver / Rejeter / Différer ; le clic est routé vers la
décision métier existante (`POST /recommendations/{id}/decision`, OPP-094).

- `app.discord_review` : builders purs (payload embed + boutons), encodage
  `custom_id` ↔ (verbe, recommandation), et `handle_interaction` qui **contrôle l'identité
  du cliqueur** (allowlist, cf. ci-dessous) puis route un clic autorisé vers un décideur
  injecté (idempotent — le back autorise la re-validation).
- `app.discord_authz` : autorisation des interactions — extrait l'identité Discord
  (`member.user` en salon, `user` en message privé) et la confronte à une `ReviewerAllowlist`.
  Un clic hors allowlist reçoit un refus **éphémère** et **n'enregistre aucune décision**.
- `app.discord_transport` : envoi via `urllib` (**aucune dépendance**), transport
  **injectable** — les tests n'ont besoin d'aucun serveur Discord.
- `DISCORD_BOT_TOKEN` porte le token du bot (en-tête `Authorization` sortant, jamais en dur).
  `DISCORD_REVIEWER_IDS` (CSV d'IDs Discord) définit **qui** peut valider — **fail-closed** :
  absente ou vide, personne n'est autorisé. La garantie d'authenticité du canal
  (signature / token) prouve « vient de Discord » ; l'allowlist prouve « d'une personne
  autorisée » — les deux sont nécessaires.

### Récepteur live des clics — gateway (option B)

`hermes.discord_gateway` connecte un **bot** à la gateway Discord (connexion **sortante**,
aucune URL publique, rien d'exposé sur la machine) et route chaque clic de bouton vers la
décision métier, en process. La logique risquée reste isolée du réseau :

- **pur/testable** : `build_decider` (le `decide` réel : verbe → statut →
  `record_human_decision`) et `process_interaction` (routage résilient — allowlist appliquée,
  jamais d'exception qui ferait tomber la boucle) ;
- **coquille async** (`run_gateway`/`main`) : connexion, heartbeat et reconnexion délégués à
  `discord.py`, importé **paresseusement**. La dépendance est **confinée à l'extra `[discord]`** :
  le cœur reste sans dépendance et testable sans elle.

```bash
pip install -e ".[discord]"                 # installe discord.py (hors cœur)
export DISCORD_BOT_TOKEN=...                 # requis
export DISCORD_REVIEWER_IDS=123,456          # requis : reviewers autorisés (fail-closed)
python -m hermes.discord_gateway            # se connecte et écoute les clics
```

Voie B tranchée vs endpoint HTTP signé (A) : pas d'exposition machine ni de migration de
persistance. Vercel + base hébergée reste la cible produit ultérieure.

**Mise en route pas à pas** (création du bot, intents/permissions minimaux, `.env`,
lancement) : voir [`docs/runbook-bot-discord.md`](docs/runbook-bot-discord.md). Le gabarit
de configuration versionné (sans secret) est [`.env.example`](.env.example).

## Lancer la boucle push (offre → run → lettre → carte Discord)

`hermes.push_runner` est l'**adaptateur mince** qui exécute la boucle *push* de bout en
bout : ingestion d'une offre collée → run Hermes → résolution amont → génération de lettre
(Ollama) → envoi des cartes de revue dans Discord. Toute la logique vit dans les modules
testés en aval ; le runner ne fait que les câbler et lire l'environnement.

```bash
export DISCORD_BOT_TOKEN=...                    # requis (transport Discord)
export DISCORD_CHANNEL_ID=123456789            # requis : salon où poster les cartes
export OPPORTUNE_CANDIDATE_ID=cand-marie        # requis : candidat ciblé
export OPPORTUNE_LLM_TIMEOUT=300                # timeout LLM (s) — défaut 300, généreux
# export OPPORTUNE_OFFER_SOURCE=collée          # optionnel : provenance de l'offre
# OLLAMA_HOST / OLLAMA_MODEL / OPPORTUNE_DB_PATH : cf. sections dédiées

pbpaste | python -m hermes.push_runner          # l'offre collée est lue sur stdin
python -m hermes.push_runner < offre.txt        # ou depuis un fichier ; stdin vide → stock existant
```

Le timeout LLM est **volontairement large** (défaut 300 s) : une lettre complète dépasse le
défaut 60 s d'`app.llm` à froid.

Un échec partiel du lot lève `BatchReviewError` : le lot **s'arrête à la première carte en
échec** en rapportant celles déjà poussées (la progression n'est pas perdue).

**Idempotence du re-run (OPP-131)** : le runner suit les cartes poussées dans un
`SubmissionStore` (`app.submission_store`) et n'en **re-pousse aucune tant qu'elle est
encore en attente** — chaque carte est mémorisée **dès son envoi**, donc même une reprise
après un `BatchReviewError` (ou une interruption) ne redouble jamais les cartes déjà poussées. Ce suivi est **distinct du statut de validation**
(une carte reste `pending` jusqu'au clic humain, pour rester validable via Discord, OPP-125).
Si un message est supprimé côté Discord, `SubmissionStore.forget(recommendation_id)` autorise
une re-soumission au prochain run.

## Collecter des offres réelles (OPP-120 / OPP-122)

La collecte réelle branche une **source** (port `SourceOffres`) sur le socle de collecte
(OPP-119) : dédoublonnage **avant** analyse LLM, normalisation, persistance. Chaque runner ne
fait que lire sa configuration, assembler sa source et lancer la passe (briques communes dans
`app.collection_runner`). Les runners affichent un bilan (collectées / persistées / doublons /
échecs) et sortent en code non nul si la **source** a échoué (quota, réseau, identifiants) ;
les échecs d'analyse **par offre** sont consignés sans interrompre la passe.

### RSS — connecteur actif, sans secret

`app.rss_runner` ingère des offres depuis des **flux RSS/Atom** d'alertes emploi (`app.rss_feed`
parse RSS 2.0 / RDF / Atom ; `app.rss_source` fetch SSRF-safe + nettoyage HTML du contenu). Aucun
identifiant requis : c'est le connecteur le plus simple et le plus pérenne.

Le contenu d'un article RSS étant du HTML, ce runner **requiert l'extra `scrape`** (BeautifulSoup) ;
il échoue d'emblée avec un message clair s'il est absent.

```bash
pip install -e ".[scrape]"                       # requis : nettoyage HTML du contenu des flux
export OPPORTUNE_LLM_TIMEOUT=300                # timeout LLM (s) pour l'analyse d'intake
# OLLAMA_HOST / OLLAMA_MODEL / OPPORTUNE_DB_PATH : cf. sections dédiées

python -m app.rss_runner --feed https://exemple.fr/offres.rss --feed https://autre.fr/flux.xml
RSS_FEED_URLS="https://a.rss,https://b.xml" python -m app.rss_runner   # ou via l'environnement
```

Options : `--feed` (répétable) ou `RSS_FEED_URLS` (séparé par virgules/espaces), `--max` (plafond
d'offres sur l'ensemble des flux, défaut 500). Les flux sont parcourus en séquence ; l'échec d'un
flux (réseau, XML malformé) arrête la passe en `source_error`, les offres déjà émises restant acquises.

### Adzuna — connecteur actif

`app.adzuna_runner` interroge l'[API Adzuna](https://developer.adzuna.com) (marché français),
en ciblant par défaut les contrats permanents (≈ CDI). Inscription gratuite et instantanée sur
developer.adzuna.com : l'`app_id` et l'`app_key` sont affichés aussitôt (cf. `.env.example`).

```bash
export ADZUNA_APP_ID=...                        # requis
export ADZUNA_APP_KEY=...                        # requis
export OPPORTUNE_LLM_TIMEOUT=300                # timeout LLM (s) pour l'analyse d'intake
# OLLAMA_HOST / OLLAMA_MODEL / OPPORTUNE_DB_PATH : cf. sections dédiées

python -m app.adzuna_runner --what "python" --where "Paris" --max 100
python -m app.adzuna_runner --tous-contrats     # ne pas restreindre aux CDI
```

Options : `--what`, `--where` (filtres de recherche), `--max` (plafond d'offres, défaut 200 —
modéré pour ménager le quota gratuit de 2 500 appels/mois), `--tous-contrats` (lève le filtre
CDI). Le runner pagine jusqu'au total annoncé (`count`) ou au plafond.

### France Travail — connecteur dormant

`app.france_travail_runner` interroge l'API officielle France Travail « Offres d'emploi ».
⚠️ **Cette API n'est plus en accès self-service** : elle a été restreinte (usage automatisé/IA
massif) et nécessite désormais une demande d'accès + l'acceptation d'un contrat de licence sur
[francetravail.io](https://francetravail.io). Le connecteur est **prêt mais inactif** tant que
l'accès n'est pas accordé.

```bash
export FRANCE_TRAVAIL_CLIENT_ID=...             # requis : identifiant de l'application
export FRANCE_TRAVAIL_CLIENT_SECRET=...         # requis : secret (SECRET, jamais en dur)

python -m app.france_travail_runner --mots-cles "python" --max 150
python -m app.france_travail_runner --code-rome M1805 --commune 75056
```

Options : `--mots-cles`, `--code-rome`, `--commune`, `--max` (plafond borné à la fenêtre dure
de l'API, `range` ≤ 1000/1149, soit ~1150 offres par requête ; au-delà il faudrait fragmenter
par date/département, hors périmètre).
