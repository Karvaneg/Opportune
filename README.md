# Opportune

Assistant de candidature (analyse d'offres, scoring, personnalisation et suivi), avec intégration Notion pour le pilotage des tickets.

## Prérequis

- **Node.js ≥ 18** (le projet utilise le lanceur de tests natif `node --test` et l'API `node:test`). Développé et testé avec Node 24.
- **npm** (fourni avec Node.js).
- Un **espace Notion** avec une intégration et une base de données de tickets (pour `npm start`).

Aucune autre dépendance système : le moteur est en JavaScript pur, sans base de données externe (stockage sur disque en JSON dans `data/`).

## Installation

```bash
git clone <url-du-dépôt> Opportune
cd Opportune
npm install
```

## Configuration

La configuration locale se fait via un fichier `.env.local` (gitignoré, jamais commité). Partir du modèle fourni :

```bash
cp .env.example .env.local
```

Puis renseigner les valeurs dans `.env.local` :

| Variable | Rôle | Obligatoire |
|---|---|---|
| `NOTION_TOKEN` | Token d'intégration Notion (secret) — voir https://www.notion.so/my-integrations | oui (pour `npm start`) |
| `NOTION_DATABASE_ID` | ID de la base (database) Notion | oui |
| `NOTION_DATA_SOURCE_ID` | ID de la data source interrogée par le code (`@notionhq/client` v5) | oui |
| `NOTION_TICKET_ID_PROP` | Propriété portant l'identifiant du ticket (défaut : `ID`) | non |
| `NOTION_STATUS_PROP` | Propriété statut à mettre à jour (défaut : `Statut`) | non |
| `NOTION_DOING_OPTION` | Nom exact de l'option « en cours » (ex. `In Progress`) | non |
| `NOTION_DONE_OPTION` | Nom exact de l'option « terminé » (ex. `Done`) | non |
| `LOG_LEVEL` | Seuil des logs applicatifs : `debug`, `info`, `warn`, `error` (défaut : `info`) | non |

Le fichier `.env.local` est chargé automatiquement au démarrage (via `dotenv`, cf. `src/notion/client.js`). Les secrets ne sont jamais journalisés (masquage assuré par le logger et `config/secrets`).

## Lancement

```bash
npm start
```

Récupère les tickets depuis Notion et affiche le prochain ticket recommandé, les tickets urgents et les priorités suggérées.

## Tests

```bash
npm test
```

Lance l'intégralité de la suite via `node --test` (aucun framework externe).

## Structure du projet

```
src/
  config/     Configuration et secrets (chargement .env, masquage)
  errors/     Hiérarchie d'erreurs typées
  fixtures/   Jeux de données de test (offres d'exemple)
  logging/    Logger applicatif structuré
  models/     Modèles de données + persistance JSON (profil, offre, candidature…)
  notion/     Intégration Notion (client, requêtes, mutations)
  services/   Cœur métier (analyse, scoring, personnalisation, suivi)
  display/    Formatage pour l'affichage terminal
  index.js    Point d'entrée (npm start)
docs/         Documentation projet (vision, definition of done)
scripts/      Scripts utilitaires
data/         Données locales persistées (gitignoré)
```

## Données locales

Les données personnelles et les documents générés sont stockés en JSON sous `data/` (dossier gitignoré). Ils restent donc uniquement sur votre machine.
