# ADR 0001 — Hermes comme orchestrateur externe (cadrage, non intégré)

- **Statut** : Proposé — **différé** (documenté maintenant, pas intégré)
- **Date** : 2026-09-03
- **Contexte ticket** : OPP-079 (Epic E7 — Infrastructure et sécurité)
- **Décideurs** : équipe Opportune

## Contexte

La stack cible V2 (Python) dispose désormais de son socle d'infrastructure :
environnement Docker/WSL (OPP-071), persistance SQLite (OPP-072), accès au LLM local
Ollama/Ministral (OPP-073), et — avec OPP-079 — un **contrat d'intégration LLM**
(`app.llm_client.LLMClient`) découplé d'Ollama.

La question se pose d'introduire **Hermes**, un orchestrateur externe qui piloterait
les tâches (collecte, analyse, génération, relances) au-dessus du métier Python. Le
risque est d'ajouter cette couche d'orchestration **avant** d'avoir prouvé qu'une
seule boucle métier fonctionne de bout en bout en Python.

## Décision

**Ne pas intégrer Hermes à ce stade.** On le documente comme cadrage (le présent ADR)
et on conditionne son introduction à un prérequis clair :

> Prouver **une seule boucle métier de bout en bout** en Python
> (`profil candidat → prompt structuré → réponse Ministral → résultat validé`)
> **avant** d'ajouter un orchestrateur externe.

Séquence de travail retenue :

1. **OPP-079** — contrat LLM (`LLMClient`, `LLMResponse`, mock, erreurs typées) ✅
2. **OPP-075** — premier cas métier Python (une vertical slice minimale)
3. Tests d'intégration réels avec Ollama
4. Comparaison du comportement avec la base Node.js
5. **Seulement ensuite** — Hermes comme orchestrateur externe (ré-ouvrir cet ADR)

## Points à cadrer pour Hermes (à instruire au moment de l'intégration)

Ces questions sont ouvertes et **volontairement non tranchées** ici ; elles servent de
grille d'instruction le jour où l'étape 5 sera atteinte.

- **Rôle exact** — périmètre d'Hermes vs. le métier Python : qu'orchestre-t-il
  (enchaînement des tâches, planification, reprise) et que garde le métier
  (logique de candidature, scoring, génération) ?
- **Déclenchement des tâches** — cron, file d'attente, événements, ou déclenchement
  manuel ? Fréquence et idempotence attendues.
- **Protocole d'échange avec Python** — CLI, HTTP local, file de messages ? Format
  des messages, versionnage du contrat, frontière de (dé)sérialisation.
- **Permissions** — quels droits Hermes détient-il (accès DB, réseau sortant, envoi
  réel de candidatures) ? Principe de moindre privilège ; secrets et leur portée.
- **Reprise sur erreur** — nouvelles tentatives, back-off, idempotence des étapes,
  reprise partielle d'une boucle interrompue, journalisation/traçabilité.
- **Validation humaine** — où s'insère le point de contrôle humain (déjà présent côté
  Node via l'adaptateur Discord) ? Hermes doit **respecter** le blocage d'envoi sans
  confirmation, pas le contourner.

## Conséquences

- **Positives** : on limite le sur-engineering ; le métier reste orchestrable « à la
  main » (script/CLI) tant que la boucle n'est pas prouvée ; le contrat `LLMClient`
  garde le métier indépendant de toute couche d'orchestration.
- **Négatives / risques** : pas d'automatisation de bout en bout à court terme ; le
  cadrage Hermes devra être réévalué (cet ADR pourra être remplacé par un ADR de
  décision effective).

## Références

- OPP-079 — Contrat d'intégration LLM (ce livrable)
- OPP-073 — Accès Ollama/Ministral (`app.llm`)
- `docs/vision.md`, `docs/definition-of-done.md`
