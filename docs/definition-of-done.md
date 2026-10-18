# Definition of Done

> Un ticket n'est **Done** que lorsque **tous** les critères ci-dessous sont
> satisfaits. Cette DoD reflète les pratiques réellement tenues sur Opportune ;
> elle sert de garde-fou partagé, pas de formalité.

## 1. Fonctionnel

- [ ] Le **critère d'acceptation** du ticket est satisfait et vérifié.
- [ ] La **logique métier** (matching, scoring, normalisation) reste **pure, déterministe
      et testable sans LLM ni réseau** ; les appels LLM (Ollama/Ministral, pour l'analyse
      et la rédaction) passent par un contrat injectable, mocké dans les tests.
- [ ] Les cas limites et les entrées vides/incomplètes sont gérés proprement.

## 2. Code

- [ ] **Une responsabilité par fichier** sous `python/src/app/` : fonctions pures,
      services (`*_service.py`) et dépôts SQLite (`*_store.py`) séparés.
- [ ] Réutilisation avant duplication (ex. lexique de compétences partagé).
- [ ] Commentaires **en français**, densité et style cohérents avec l'existant.
- [ ] Aucune **dépendance externe** ajoutée sans justification explicite : le cœur vise
      zéro dépendance, les extras (`scrape`, `discord`) restent confinés et importés paresseusement.
- [ ] **Erreurs typées** (exceptions dédiées) là où l'appelant doit distinguer les cas.

## 3. Tests

- [ ] Tests sous `python/tests/`, avec `pytest`, couvrant le cas nominal, les cas
      limites et les erreurs.
- [ ] `pytest` **entièrement au vert**, sans test ignoré (venv `python/.venv/bin/pytest`
      ou `docker compose run --rm app pytest`).
- [ ] Les tests n'écrivent pas dans les données réelles (SQLite en mémoire / fichiers
      temporaires) et ne dépendent pas du réseau.

## 4. Fidélité et sécurité

- [ ] **Aucune invention** : CV et lettres restent strictement fidèles au profil ;
      les compétences manquantes sont signalées, jamais ajoutées (anti-invention).
- [ ] Les **secrets** sont lus depuis l'environnement / `.env.local` (gitignoré),
      **jamais commités ni journalisés**.
- [ ] **Aucun envoi** possible sans validation humaine **explicite** (sas d'envoi).

## 5. Intégration et suivi

- [ ] Travail sur une **branche dédiée** `OPP-XXX-slug`, créée depuis `main` à jour.
- [ ] **Commit conventionnel** ; PR ouverte, mergée dans `main`, branche supprimée.
- [ ] Le **ticket Notion** est passé en **Done**, statut **relu et confirmé**.

## 6. Documentation

- [ ] Le code est auto-documenté ; la documentation (`docs/`, `CLAUDE.md`) est mise
      à jour si la vision, l'architecture ou les conventions changent.

---

Voir aussi : [`docs/vision.md`](./vision.md) (vision produit et stack cible),
`CLAUDE.md` (contexte et conventions du dépôt).
