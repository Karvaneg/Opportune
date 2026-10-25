# ADR 0005 — Hermes, orchestrateur intégré (couche in-process)

- **Statut** : Accepté — **en vigueur**
- **Date** : 2026-10-25
- **Contexte ticket** : OPP-204 (Epic E9 — Orchestration)
- **Décideurs** : équipe Opportune
- **Remplace** : [`ADR 0001`](0001-hermes-orchestrateur-externe.md)

## Contexte

L'[ADR 0001](0001-hermes-orchestrateur-externe.md) avait **différé** Hermes : le documenter
comme cadrage mais **ne pas l'intégrer**, et le réserver à un orchestrateur **externe**
(protocole CLI / HTTP / file de messages) à instruire une fois prouvée une boucle métier de
bout en bout en Python. Il prévoyait explicitement d'être **« ré-ouvert / remplacé par un ADR
de décision effective »** le jour de l'intégration.

Ce jour est passé (Epic E9). La boucle métier a été prouvée, puis Hermes a été **réellement
intégré** — mais **pas** sous la forme imaginée en 0001. Le présent ADR acte la décision telle
qu'elle a été prise dans le code, et clôt 0001.

## Décision

**Hermes est intégré comme une couche d'orchestration _in-process_**, entre le métier
(`app/`) et l'API HTTP (`api/`) — et **non** comme un orchestrateur externe doté d'un protocole
d'échange.

`HermesOrchestrator` (`python/src/hermes/orchestrator.py`) **coordonne** les services métier
sans réimplémenter leur logique : d'un `candidate_id`, il déroule
`RecommendationService.recommend → DecisionService.decide` (décisions `pending` persistées),
journalise chaque exécution (`HermesRun` / `RunRepository`) et offre le **point d'entrée unique
de la validation humaine**.

Les questions laissées ouvertes par 0001 sont tranchées **par le code** :

- **Rôle exact** — Hermes **enchaîne** recommandation → décision et **journalise** les runs ;
  toute la logique (scoring, décision, actions) reste dans `app/`. Il ne reclasse ni ne filtre
  les recommandations ; il délègue.
- **Protocole d'échange** — **aucun** : Hermes est du Python appelé **directement** par `api/`
  (`HermesApi.dispatch` → orchestrateur). Pas de frontière de (dé)sérialisation, pas de service
  séparé à déployer. C'est l'écart majeur avec 0001.
- **Déclenchement** — **à la demande**, jamais de cron ni de file : via l'API HTTP pilotée par le
  front (`POST /candidates/{id}/recommendations`, runs), et via les adaptateurs minces
  `hermes.push_runner` (boucle push) et `hermes.discord_gateway` (clics de revue).
- **Permissions** — Hermes n'a **aucun privilège propre** : il hérite du cadre local-first
  mono-utilisateur (cf. [`ADR 0003`](0003-auth-local-first-sans-jeton.md)).
- **Reprise sur erreur** — chaque erreur **par offre** est capturée dans le run et **n'interrompt
  pas** les suivantes ; la persistance des décisions est **idempotente** (upsert sur le couple
  candidat/offre), donc une ré-exécution reprend proprement.
- **Validation humaine** — **respectée, jamais contournée** : Hermes ne produit que des décisions
  `pending` ; la validation (`approved`/`rejected`/`deferred`) est explicite via
  `validate_decision` / `record_human_decision`.

## Conséquences

- **Positives** : testabilité maximale (collaborateurs injectés, dépôts SQLite en mémoire, aucun
  réseau) ; pas de service externe à exploiter ni de contrat réseau à versionner ; le métier reste
  découplé de l'orchestration. L'anti-sur-engineering visé par 0001 est tenu — autrement que prévu.
- **Négatives / assumées** : pas d'orchestration multi-process ni de planification autonome
  (cron/queue) à ce stade ; si un tel besoin émerge (collectes planifiées, exécutions longues hors
  requête HTTP), il fera l'objet d'un nouvel ADR plutôt que d'un détournement de cette couche.

## Références

- `python/src/hermes/orchestrator.py` — `HermesOrchestrator`
- `python/src/api/app.py`, `python/src/api/server.py` — câblage de Hermes dans l'API
- [`ADR 0001`](0001-hermes-orchestrateur-externe.md) — le cadrage différé que cet ADR remplace
- [`ADR 0003`](0003-auth-local-first-sans-jeton.md) — cadre local-first
- [`python/README.md`](../../python/README.md) — les trois couches `app/` · `hermes/` · `api/`
