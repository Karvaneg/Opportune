# Validation humaine — revue Discord (interface historique)

> ⚠️ **Interface historique (MVP).** La validation courante se fait désormais dans le
> **frontend web** (cf. [`frontend/README.md`](../../frontend/README.md)). Le chemin Discord
> décrit ici — ainsi que la boucle push — reste **fonctionnel et testé**, mais n'est plus
> l'interface de référence ; il est conservé comme option et pour l'historique
> (cf. [`docs/vision.md`](../../docs/vision.md)).

## Revue push-to-triage

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

## Récepteur live des clics — gateway (option B)

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
lancement) : voir [`runbook-bot-discord.md`](runbook-bot-discord.md). Le gabarit
de configuration versionné (sans secret) est [`../.env.example`](../.env.example).

## Lancer la boucle push (offre → run → lettre → carte Discord)

`hermes.push_runner` est l'**adaptateur mince** qui exécute la boucle *push* de bout en
bout : ingestion d'une offre collée → run Hermes → résolution amont → génération de lettre
(Ollama) → envoi des cartes de revue dans Discord. Toute la logique vit dans les modules
testés en aval ; le runner ne fait que les câbler et lire l'environnement.

```bash
export DISCORD_BOT_TOKEN=...                    # requis (transport Discord)
export DISCORD_CHANNEL_ID=123456789            # requis : salon où poster les cartes
export OPPORTUNE_CANDIDATE_ID=ma-recherche      # requis : recherche ciblée
export OPPORTUNE_LLM_TIMEOUT=300                # timeout LLM (s) — défaut 300, généreux
# export OPPORTUNE_OFFER_SOURCE=collée          # optionnel : provenance de l'offre
# OLLAMA_HOST / OLLAMA_MODEL / OPPORTUNE_DB_PATH : cf. README back

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
