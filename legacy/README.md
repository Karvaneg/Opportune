# Legacy — V1 Node.js (MVP CLI historique)

Ce dossier contient le **MVP en ligne de commande** d'origine d'Opportune, écrit en
Node.js. Il **n'est plus la cible produit** : le développement se fait désormais sur la
V2 (back Python dans [`../python/`](../python/), front React dans
[`../frontend/`](../frontend/)).

Il est conservé **pour référence** — la logique métier a été migrée vers la V2, et cet
historique documente d'où vient le projet. Rien ici n'est exécuté par la CI.

## Ce que faisait la V1

Récupérer les tickets depuis Notion et suggérer le prochain à traiter, avec un stockage
local en JSON. Intégration Notion via `@notionhq/client`.

## L'exécuter (optionnel)

Depuis ce dossier :

```bash
npm install
cp .env.example .env.local   # renseigner NOTION_TOKEN, NOTION_DATABASE_ID, NOTION_DATA_SOURCE_ID
npm start                    # affiche le prochain ticket recommandé
npm test                     # suite V1 via node --test
```

Les données locales V1 sont stockées en JSON sous `data/` (gitignoré) et ne quittent pas
votre machine.
