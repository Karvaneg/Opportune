# ADR 0004 — Pivot de la V1 Node.js vers la V2 Python

- **Statut** : Accepté — **en vigueur**
- **Date** : 2026-10-25
- **Contexte ticket** : OPP-203 (Epic E7 — Infrastructure et sécurité)
- **Décideurs** : équipe Opportune

## Contexte

Le MVP d'Opportune (V1) a été écrit en **Node.js** : un outil en ligne de commande qui
récupère les tickets depuis Notion et suggère le prochain à traiter, avec un stockage local
en JSON (cf. [`legacy/`](../../legacy/)). Ce choix répondait à l'objectif d'un MVP : **valider
vite une hypothèse produit**, sur un terrain connu (JavaScript/TypeScript, déjà utilisé côté
front), avec le SDK Notion officiel sous la main et un minimum de friction.

Une fois la boucle produit dégrossie, le cœur réel d'Opportune s'est précisé : **analyse
d'offres par LLM local, extraction de texte (CV PDF), scoring et matching sémantique,
orchestration de tâches**. La question s'est posée de continuer en Node ou de réécrire le
cœur dans une stack mieux adaptée à ce domaine.

## Décision

**Réécrire le cœur métier en Python** (la V2, sous [`python/`](../../python/)), et conserver
la V1 Node.js uniquement comme référence historique archivée.

Ce n'est pas un désaveu du choix initial : le MVP Node a **fait son travail** — prouver que la
valeur était là — avant qu'on investisse dans une fondation durable. C'est une progression
**MVP → produit**, pas une correction d'erreur.

Motifs du choix Python :

- **Adéquation au domaine** — LLM (Ollama), NLP, extraction PDF, scoring : l'écosystème et les
  idiomes naturels de ces sujets sont en Python.
- **Architecture testable** — la V2 sépare nettement trois couches (métier `app/` /
  orchestration `hermes/` / API `api/`), avec une **logique métier pure, testable sans LLM ni
  réseau**. C'est ce qui fait passer d'un script à un produit maintenable.
- **Zéro dépendance de production** — le cœur, l'orchestrateur et l'API tiennent sur la
  **bibliothèque standard** (`sqlite3`, `urllib`, `http.server`). Surface réduite, moins de
  dette, et surtout un **packaging desktop** (binaire PyInstaller en sidecar de l'app Tauri 1.0)
  nettement plus simple à embarquer qu'un runtime Node + `node_modules`.
- **Local-first durable** — tout tourne sur la machine de l'utilisateur, aucune donnée ne sort
  (cf. [`ADR 0003`](0003-auth-local-first-sans-jeton.md)).

## Conséquences

- **Positives** : stack alignée sur le cœur IA du produit ; architecture en couches testable ;
  base saine pour la distribution grand public (Opportune 1.0, app desktop). Le dépôt public
  ne montre plus qu'**une seule stack active** (V1 archivée sous `legacy/`, OPP-200).
- **Négatives / assumées** : coût d'une réécriture du cœur ; une période de **double stack**
  pendant la migration (désormais close) ; la logique métier V1 (adaptateurs Discord, scoring
  historique) a dû être re-portée plutôt que réutilisée telle quelle.

## Références

- [`legacy/README.md`](../../legacy/README.md) — la V1 Node.js archivée
- OPP-200 — archivage de la V1 sous `legacy/`
- [`ADR 0001`](0001-hermes-orchestrateur-externe.md) — Hermes comme orchestrateur
- [`ADR 0003`](0003-auth-local-first-sans-jeton.md) — local-first sans jeton
- [`docs/vision.md`](../vision.md)
