# Runbook — bot Discord (récepteur live des clics)

Mode d'emploi pour faire tourner en local la boucle de validation Discord :
**push** des cartes (`hermes.push_runner`, OPP-128) et **receive** des clics
(`hermes.discord_gateway`, OPP-125). Principe directeur : **moindre privilège** — le bot
n'obtient que ce qu'il faut pour poster des cartes et recevoir les clics de boutons.

> ⚠️ **Aucun secret ne se commite.** Les valeurs vont dans `python/.env` (gitignoré) ;
> seul `python/.env.example` (sans secret) est versionné.

## 1. Créer l'application et le bot

1. Ouvrir le [Discord Developer Portal](https://discord.com/developers/applications) →
   **New Application**, la nommer (p. ex. `Opportune`).
2. Onglet **Bot** → **Add Bot** → **Reset Token** → copier le token.
   C'est la valeur de `DISCORD_BOT_TOKEN` (secret, jamais partagé ni commité).

## 2. Intents — le strict minimum

Les interactions de **composants** (clics de boutons) arrivent par la gateway **sans intent
privilégié**. Dans l'onglet **Bot** › *Privileged Gateway Intents*, laisser **tout
désactivé** :

- ❌ Presence Intent
- ❌ Server Members Intent
- ❌ Message Content Intent

Le code se connecte d'ailleurs avec `discord.Intents.none()`.

## 3. Inviter le bot avec des permissions minimales

Onglet **OAuth2** › **URL Generator** :

- **Scopes** : `bot` uniquement (pas besoin de `applications.commands` : les boutons sont
  portés par des messages postés par le bot, pas par des slash commands).
- **Bot Permissions** : `View Channel` + `Send Messages` (valeur `3072`).

Ouvrir l'URL générée, choisir le serveur, autoriser. Le bot doit avoir accès au salon cible.

> Il te faut donc un serveur Discord **déjà créé** pour l'y inviter. Si ce n'est pas le cas,
> crée-le d'abord (cf. § 4.a) puis reviens ouvrir l'URL.

> ⚠️ **Onglet _Installation_ — deux réglages, ne pas les confondre.** Sur une app **privée**
> (Public Bot désactivé), Discord bloque avec *« Une application privée ne peut pas avoir de
> lien d'autorisation par défaut… »*. Le déblocage tient à **deux** réglages de cet onglet,
> à sauvegarder ensemble :
>
> 1. **Install Link** (menu déroulant) → **None / Aucun**. C'est *ce* réglage qui lève
>    l'erreur « application privée » (le lien d'autorisation par défaut n'est permis que pour
>    une app publique).
> 2. **Installation Contexts** → **« Installation sur un serveur » (Guild Install) activé**.
>    Indispensable : sans lui, l'ajout du bot à un serveur échoue avec *« type d'installation
>    non prise en charge »*.
>
> Ne PAS se contenter de cocher « Installation pour un utilisateur » : le bot doit être
> installé **sur un serveur** pour poster dans un salon. L'invitation réelle se fait ensuite
> via l'URL Generator ci-dessus (scope `bot`), pas via ce lien par défaut.

## 4. Récupérer les identifiants

> ⚠️ **Deux endroits distincts.** Les étapes 1-3 se passent dans le **portail développeur**
> (création de l'appli et du bot). Le **serveur** et le **salon**, eux, n'existent pas là-bas :
> ils se créent dans le **client Discord** (l'app de chat habituelle). `DISCORD_CHANNEL_ID` et
> `DISCORD_REVIEWER_IDS` s'y récupèrent, pas dans le portail.

### 4.a Créer le serveur et le salon (si tu n'en as pas déjà)

Dans le client Discord :

1. Colonne de gauche → **+** (*Ajouter un serveur*) → *Créer mon propre serveur*. C'est là
   qu'atterrira le bot invité à l'étape 3.
2. Dans ce serveur, créer (ou réutiliser) un **salon textuel** cible où les cartes seront
   postées (p. ex. `#candidatures`).

### 4.b Copier les identifiants

Activer le **Mode développeur** (Discord › Paramètres › Avancés › Mode développeur), puis,
toujours dans le client Discord :

- **Salon cible** : clic droit sur le salon → *Copier l'identifiant du salon* →
  `DISCORD_CHANNEL_ID`.
- **Reviewers autorisés** : clic droit sur chaque personne → *Copier l'identifiant* →
  `DISCORD_REVIEWER_IDS` (séparés par des virgules).

> Ne pas confondre avec l'*Application ID* (Client ID) du portail : celui-ci sert uniquement à
> générer l'URL d'invitation (étape 3) et **ne va pas** dans le `.env`.

> 🔒 L'allowlist est **fail-closed** : si `DISCORD_REVIEWER_IDS` est vide, personne ne peut
> valider. La garantie d'authenticité du canal (token du bot) prouve « vient de Discord » ;
> l'allowlist prouve « d'une personne autorisée » — les deux sont nécessaires.

## 5. Configurer l'environnement

```bash
cd python
cp .env.example .env          # puis renseigner les valeurs (voir .env.example)
```

Variables indispensables pour le bot : `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`,
`DISCORD_REVIEWER_IDS`. Pour la génération de lettre côté push : `OLLAMA_HOST` /
`OLLAMA_MODEL` (cf. README « LLM local »).

> 🐧 **WSL2 + Ollama natif Windows.** Ne pas mettre `OLLAMA_HOST=http://localhost:11434` :
> depuis WSL2, `localhost` désigne WSL, pas l'hôte Windows où tourne Ollama → `Connection
> refused`. Utiliser l'IP de la passerelle WSL, récupérable par
> `ip route | awk '/^default/{print $3}'` (souvent `172.18.224.1`), d'où
> `OLLAMA_HOST=http://172.18.224.1:11434`. Cette IP peut changer au redémarrage de WSL ;
> la revérifier si le LLM devient injoignable. Côté Windows, Ollama doit écouter au-delà de
> `localhost` (`OLLAMA_HOST=0.0.0.0`) et le pare-feu autoriser le port `11434`.

## 6. Installer la dépendance Discord (extra confiné)

`discord.py` n'est **pas** une dépendance du cœur : elle vit dans l'extra `[discord]`.

```bash
pip install -e ".[discord]"
```

## 7. Préparer la base (données de démo)

Sans profil candidat en base, le run push échoue (`UnknownCandidateError`). Le seed pose un
profil + une offre de démo alignés (score élevé → `postuler`, donc une carte à pousser) :

```bash
set -a && source .env && set +a          # charge OPPORTUNE_CANDIDATE_ID, OPPORTUNE_DB_PATH…
python -m hermes.seed_demo               # idempotent (rejouable sans doublon)
```

> Utilitaire de **démo** : il écrit dans la base pointée par `OPPORTUNE_DB_PATH`. Il ne
> **remplace pas** un profil déjà présent sous `OPPORTUNE_CANDIDATE_ID` (tes données réelles
> sont préservées) : il ne pose le profil de démo que s'il manque. Pour un vrai usage,
> alimente la base par tes propres offres (`hermes.push_runner` sait ingérer une offre collée
> sur stdin).

## 8. Lancer

Charger le `.env` dans le shell puis démarrer les deux côtés (deux terminaux) :

```bash
# charge les variables (une option simple parmi d'autres)
set -a && source .env && set +a

# terminal A — récepteur live des clics (reste connecté)
python -m hermes.discord_gateway

# terminal B — pousse une offre collée en revue
pbpaste | python -m hermes.push_runner        # macOS ; sous Linux : xclip -o | ...
python -m hermes.push_runner < offre.txt      # ou depuis un fichier
```

Une carte apparaît dans le salon avec **Approuver / Rejeter / Différer**. Un clic d'un
reviewer autorisé enregistre la décision ; un clic hors allowlist reçoit un refus éphémère
et **n'enregistre rien**.

## Sécurité — rappel

- **Secrets** : uniquement dans `.env` (gitignoré). Ne jamais les committer ni les logger.
- **Moindre privilège** : aucun intent privilégié, permissions `View Channel` + `Send Messages`.
- **Rotation** : en cas de fuite du token, *Reset Token* dans le portail invalide l'ancien.
- **ToS** : usage conforme aux conditions d'utilisation de Discord.
