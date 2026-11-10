# Opportune — coquille desktop (Tauri, OPP-192)

Transforme les processus de dev (API Python + front Vite + moteur LLM) en **une app
de bureau**. Tauri ne porte aucune logique métier : il lance **deux sidecars**,
attend que l'API réponde, ouvre une fenêtre dessus, et les arrête à la fermeture.
Front et données viennent du même origin (l'API) : aucun CORS.

- **API** (`opportune-api`, OPP-190) : sert le front compilé (OPP-191) sur
  `127.0.0.1:8000` (port surchargeable par `OPPORTUNE_API_PORT`, lu à la fois par la
  coquille et par l'API). La fenêtre s'ouvre une fois ce port prêt.
- **Ollama** (OPP-194, OPP-251) : le moteur LLM local. Embarqué en **version CPU
  seule** (cf. `sync-ollama.sh`). Le téléchargement du **modèle** reste géré par le
  front/API (flux OPP-193, `/system/llm/*`).

### Quel Ollama l'app utilise (OPP-251)

Pour ne pas surcharger la machine, l'app réutilise ce qui est déjà installé. Au
démarrage, `main.rs` sonde `/api/version` à l'adresse de l'`OLLAMA_HOST` de la
personne (si elle en a défini un) et sur `127.0.0.1:11434`, en parallèle et dans
un thread de fond :

| Situation | Ce que fait l'app |
|---|---|
| Un Ollama de version ≥ 0.13.1 répond | Elle le réutilise, sans lancer le sien. Les modèles suivent la configuration de cet Ollama (souvent `~/.ollama`). |
| Un Ollama récent répond, mais l'app a déjà téléchargé le modèle dans son propre dossier et cet Ollama ne l'a pas | Elle lance l'Ollama embarqué sur un port libre, pour ne pas télécharger le modèle une seconde fois. |
| Aucun Ollama ne répond, `11434` est libre | Elle lance l'Ollama embarqué sur `11434`. |
| `11434` est tenu par un autre service | Elle lance l'Ollama embarqué sur un port libre choisi par le système. |
| L'Ollama qui répond est plus ancien que 0.13.1 | Elle ne le réutilise pas (`ministral-3` exige 0.13.1) et lance l'Ollama embarqué sur un port libre. |

L'adresse retenue est passée à l'API par `OLLAMA_HOST`. Après avoir lancé l'Ollama
embarqué, l'app attend qu'il réponde sur son port (5 s au plus). S'il s'arrête
avant (port pris entre-temps par un autre programme), elle réessaie sur un autre
port, trois fois au plus. Si aucun Ollama n'est utilisable,
l'API reçoit une adresse où rien n'écoute et le front affiche « moteur indisponible ».

Quand l'app lance l'Ollama embarqué, elle choisit son dossier de modèles, dans
cet ordre (modèle = `OLLAMA_MODEL`, défaut `ministral-3:3b`) :

1. le dossier de l'app (`ollama-models/`, à côté des bases SQLite) s'il contient
   déjà le modèle ;
2. le dossier Ollama de la personne (`OLLAMA_MODELS`, sinon `~/.ollama/models`)
   s'il contient déjà le modèle : pas de nouveau téléchargement de ~3 Go.
   `OLLAMA_NOPRUNE=1` empêche alors l'Ollama embarqué d'y supprimer des fichiers ;
3. sinon le dossier de l'app, où le modèle sera téléchargé.

Limite connue : un Ollama installé comme service système sous Linux range ses
modèles sous `/usr/share/ollama`, que l'app ne regarde pas. S'il est arrêté au
lancement d'Opportune, le modèle est téléchargé dans le dossier de l'app.

L'API note dans `llm-model-origin.json` (dossier de données) chaque modèle
qu'Opportune a téléchargé elle-même, avec le dossier où il a atterri
(`app.model_origin`). La coquille lui donne ce dossier par
`OPPORTUNE_OLLAMA_MODELS_DIR` ; il vaut `null` quand le téléchargement est passé
par l'Ollama de la personne. On distingue ainsi la copie d'Opportune d'une copie
que la personne avait déjà ou a téléchargée ensuite.

### Désinstaller depuis l'app (OPP-252)

Le bouton « Désinstaller Opportune » des réglages n'apparaît que dans l'app de
bureau. La coquille donne à l'API le type d'installation (`OPPORTUNE_INSTALL_KIND` :
`appimage`, `deb`, `rpm`, `linux-other`, `windows-nsis`, `windows-msi`, `macos` ou
`dev`), reconnu une fois au démarrage, et la présence d'un Ollama propre à la
personne (`OPPORTUNE_USER_OLLAMA` : on le réutilise, ou son dossier de modèles existe).

Déroulé, une fois les choix confirmés à l'écran :

1. L'API écrit la demande dans `uninstall-request.json` (dossier de données). Si
   Opportune avait téléchargé le modèle à travers l'Ollama de la personne, l'API
   demande d'abord à cet Ollama de le supprimer.
2. La coquille, qui regarde ce fichier deux fois par seconde, arrête l'API et
   Ollama (ils tiennent les fichiers à supprimer). Sous Windows, `taskkill /T /F`
   arrête tout l'arbre de process de chacun.
3. Elle supprime ce qui est coché : `ollama-models/` pour le modèle ; le reste du
   dossier de données, le cache et les données de la fenêtre pour « mes données ».
   Une suppression qui échoue est réessayée pendant 5 s ; si elle échoue encore,
   une fenêtre liste ce qui reste à supprimer à la main.
4. Elle lance le désinstalleur du système quand il y en a un, puis se ferme.

Si l'app est encore ouverte 20 s après la demande, l'écran le signale et rend la main.

| Installation | Ce que fait l'app à l'étape 4 |
|---|---|
| Windows, installeur `.exe` | Lance `uninstall.exe`, déposé à côté de l'exécutable. |
| Windows, installeur `.msi` | Ouvre la page « Applications installées » de Windows. |
| Linux `.deb` / `.rpm` | Rien : l'écran a affiché la commande (`sudo apt remove opportune` ou `sudo rpm -e opportune`). |
| Linux, installée sous `/usr` sans dpkg ni base RPM | Rien : l'écran renvoie au gestionnaire de paquets de la distribution. |
| Linux AppImage | Rien : l'écran a affiché le chemin du fichier à supprimer. |

Garde-fous :

- un modèle qui était là avant Opportune n'est jamais supprimé (`app.model_origin`).
  Dans l'Ollama de la personne, la copie d'Opportune se reconnaît à sa date de
  modification, notée au téléchargement : si la personne a supprimé puis
  retéléchargé le modèle, la date ne correspond plus et la copie est conservée ;
- un dossier n'est effacé que si son nom est l'identifiant de l'app ;
- une demande restée d'un lancement précédent est jetée au démarrage.

`~/.ollama` : l'Ollama embarqué y crée sa clé à son premier démarrage. Si le
dossier n'existait pas avant, la coquille le note (`created-ollama-home` dans le
dossier de données) et la désinstallation le retire, à condition qu'il ne
contienne toujours que cette clé.

L'Ollama embarqué fait partie de l'app : il part avec elle. L'Ollama personnel
n'est jamais touché, l'écran indique seulement comment le désinstaller.

## Lancer en dev

Prérequis : Rust (`rustup`), le toolchain système Tauri, et Node. Sous WSL, la
fenêtre s'affiche via WSLg (`echo $DISPLAY` doit renvoyer `:0`).

```bash
cd frontend
npm install                      # récupère @tauri-apps/cli
bash src-tauri/sync-sidecar.sh   # construit front + binaire API, place le sidecar
bash src-tauri/sync-ollama.sh    # embarque Ollama CPU (nécessite zstd : apt install zstd)
npm run tauri dev                # compile la coquille Rust et ouvre la fenêtre
```

La compilation Rust **exige** que les deux sidecars soient en place (`binaries/opportune-api-*`
et `binaries/ollama/`) : lance les deux scripts de sync d'abord, sinon le build échoue.

La **première** compilation Rust télécharge et bâtit les dépendances (plusieurs
minutes). Les suivantes sont rapides.

Sous **Windows** (PowerShell, sur l'hôte et pas dans WSL), les équivalents des deux scripts
de sync sont `sync-sidecar.ps1` et `sync-ollama.ps1` (voir « Construire les installeurs
Windows »).

## Construire les installeurs Linux

```bash
cd frontend
bash src-tauri/build-linux.sh                 # .deb + .rpm + .AppImage
bash src-tauri/build-linux.sh --bundles deb   # seulement le .deb
```

Les artefacts atterrissent sous `src-tauri/target/release/bundle/{deb,rpm,appimage}/`.
Passer par `build-linux.sh` plutôt que `tauri build` directement : le `.deb`/`.rpm`
se construisent sans rien, mais l'**AppImage** échoue sous WSL/headless sans
l'environnement que le wrapper pose (`APPIMAGE_EXTRACT_AND_RUN` pour contourner FUSE,
`LD_LIBRARY_PATH` pour que `linuxdeploy` résolve les libs Ollama). Prérequis : les
sidecars en place (`sync-sidecar.sh` + `sync-ollama.sh`).

## Construire les installeurs Windows

À lancer **sur l'hôte Windows** (PowerShell), pas dans WSL : PyInstaller et Tauri ne font pas
de cross-compilation. Partir d'un clone à jour (`git checkout main; git pull`).

Prérequis (une seule fois, ou après un changement de dépendances) : Rust (`rustup`, cible
MSVC) dans le PATH, Node/npm, et un Python avec les extras embarqués :

```powershell
py -m venv python\.venv
python\.venv\Scripts\python.exe -m pip install -e "python\[build,scrape,pdf]"
```

Puis, depuis `frontend\` :

```powershell
npm install                             # sinon « Cannot find module '@tauri-apps/…' »
pwsh -File src-tauri\sync-sidecar.ps1   # build du front + binaire API (PyInstaller)
pwsh -File src-tauri\sync-ollama.ps1    # embarque Ollama CPU (version figée, GPU retiré)
npm run tauri build                     # .msi (WiX) + .exe (NSIS)
```

`sync-ollama.ps1` n'est à relancer que si `src-tauri\binaries\ollama` est absent ou pour
changer de version d'Ollama. `sync-sidecar.ps1` est à relancer à chaque build : il recompile
le front et le binaire API.

Les artefacts atterrissent sous `src-tauri/target/release/bundle/{msi,nsis}/` (`targets: "all"`
dans `tauri.conf.json` produit les deux). Les installeurs ne sont **pas signés** : Windows
SmartScreen affiche un avertissement au premier lancement (signature : OPP-217).

**Sans installeur**, pour voir la dernière version du front servie par l'API lancée à la main :
l'API sert `frontend\dist`. Si l'interface paraît ancienne (un onglet absent, par exemple),
`dist` est périmé : lancer `npm run build` dans `frontend\`, puis relancer l'API depuis
`python\` avec le Python du venv : `.venv\Scripts\python.exe -m api.server`.

Le dépôt force les fins de ligne **LF** (`.gitattributes`) : un checkout Windows ne casse
donc pas les scripts bash partagés avec WSL.

## Pièces

- `tauri.conf.json` — config : identifiant, icônes, `externalBin` (sidecar API),
  `resources` (arbre Ollama embarqué sous `ollama/`).
- `src/main.rs` — spawn des deux sidecars (Ollama puis API), attente de l'API,
  création de la fenêtre sur `http://127.0.0.1:8000`, arrêt des sidecars à la sortie.
  Sous Windows, les sidecars sont lancés avec `CREATE_NO_WINDOW` : aucune fenêtre console
  ne s'ouvre à côté de l'app (OPP-221).
- `src/ollama_plan.rs` — décisions de démarrage d'Ollama (OPP-251), en fonctions pures :
  adresses à sonder, lecture de la version, choix entre réutilisation et Ollama embarqué,
  nom d'un modèle avec son tag, chemin de son manifeste. Testé par `cargo test` (à lancer à la main : la CI ne
  compile pas la coquille Tauri).
- `src/uninstall_plan.rs` — décisions de la désinstallation (OPP-252), en fonctions pures :
  lecture de la demande, type d'installation, éléments du dossier de données à supprimer.
- `capabilities/` — permissions Tauri accordées à la fenêtre (dont `opener`, pour ouvrir
  les liens externes dans le navigateur du système).
- `icons/` — `icon-source.svg` (badge indigo, lisible sur une barre des tâches claire ou
  sombre, OPP-220), `icon-source.png`, et les dérivés générés par
  `npx tauri icon src-tauri/icons/icon-source.png` (OPP-250) : `32x32.png`, `64x64.png`,
  `128x128.png`, `128x128@2x.png`, `icon.png` (paquets Linux), `icon.ico` (requis par
  `tauri-build` sous Windows) et les `Square*Logo.png`/`StoreLogo.png` (Windows). Les icônes
  macOS (`icon.icns`) et mobiles (`android/`, `ios/`) ne sont pas gardées.
- `sync-sidecar.sh` — copie le binaire API sous `binaries/opportune-api-<triple>`,
  nom où Tauri résout son sidecar.
- `sync-ollama.sh` — Linux : télécharge Ollama (version figée), **jette les runners GPU**
  (CUDA/ROCm/Vulkan) et dépose l'arbre CPU sous `binaries/ollama/` (`bin/` + `lib/`, ~76 Mo).
- `sync-sidecar.ps1`, `sync-ollama.ps1` — équivalents Windows des deux scripts de sync.
  Sous Windows, l'arbre Ollama a `ollama.exe` à la racine et ses runners sous `lib/ollama` ;
  `main.rs` reconnaît les deux dispositions.
- `build-linux.sh` — wrapper de `tauri build` qui pose l'environnement requis par
  l'étape AppImage (voir « Construire les installeurs Linux »).
- `binaries/`, `target/`, `gen/` — artefacts de build, non versionnés.

## Limites connues (socle 1.0)

- **Port fixe** (8000 par défaut, ou `OPPORTUNE_API_PORT`) : si le port est déjà pris
  (p. ex. un serveur de dev), le sidecar ne démarre pas. Pas de recherche automatique d'un
  port libre.
- **Icônes** : pas encore de `.icns`
  (arrivera avec l'installeur Mac).
- **Installeurs non signés** : ni le `.msi`/`.exe` Windows (OPP-217) ni les paquets Linux.
- **Build Windows/Linux** (OPP-194) : fait sur chaque OS, pas en cross-compile —
  Linux dans WSL, Windows sur l'hôte. **Mac reporté** (OPP-216, via un runner
  `macos-latest` en CI).
- **Message d'échec invisible sur Windows release** : si le sidecar ne démarre pas,
  l'erreur part sur `eprintln!`, sans console en release (`windows_subsystem =
  "windows"`). Pas encore de dialogue d'erreur natif (tauri-plugin-dialog) ;
  l'onboarding OPP-195 couvre la configuration in-app, pas ce cas.
