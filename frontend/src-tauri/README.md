# Opportune — coquille desktop (Tauri, OPP-192)

Transforme les processus de dev (API Python + front Vite + moteur LLM) en **une app
de bureau**. Tauri ne porte aucune logique métier : il lance **deux sidecars**,
attend que l'API réponde, ouvre une fenêtre dessus, et les arrête à la fermeture.
Front et données viennent du même origin (l'API) : aucun CORS.

- **API** (`opportune-api`, OPP-190) : sert le front compilé (OPP-191) sur
  `127.0.0.1:8000` (port surchargeable par `OPPORTUNE_API_PORT`, lu à la fois par la
  coquille et par l'API). La fenêtre s'ouvre une fois ce port prêt.
- **Ollama** (OPP-194) : le moteur LLM local, sur `127.0.0.1:11434`. Embarqué en
  **version CPU seule** (cf. `sync-ollama.sh`). Si un Ollama tourne déjà sur ce
  port, on le réutilise au lieu d'en lancer un second. Le téléchargement du
  **modèle** reste géré par le front/API (flux OPP-193, `/system/llm/*`).

Tout tient dans **une seule arborescence de données** (celle de l'app) : les bases
SQLite (via `OPPORTUNE_DATA_DIR`, passé au sidecar API) **et** les modèles Ollama
(via `OLLAMA_MODELS`) y sont rangés ensemble — supprimés avec l'app, sauvegardables
d'un bloc. **Réserve** : quand on réutilise un Ollama déjà lancé, ses modèles suivent
*sa* configuration (souvent `~/.ollama`), hors de notre contrôle.

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

À lancer **sur l'hôte Windows**, pas dans WSL : PyInstaller et Tauri ne font pas de
cross-compilation. Prérequis : Rust (`rustup`, cible MSVC), Node/npm, et un Python avec les
extras embarqués (`py -m venv python\.venv` puis
`python\.venv\Scripts\python.exe -m pip install -e "python\[build,scrape,pdf]"`).

```powershell
cd frontend
npm install
pwsh -File src-tauri\sync-sidecar.ps1   # build front + binaire API, place le sidecar .exe
pwsh -File src-tauri\sync-ollama.ps1    # embarque Ollama CPU (version figée, GPU retiré)
npm run tauri build                     # .msi (WiX) + .exe (NSIS)
```

Les artefacts atterrissent sous `src-tauri/target/release/bundle/{msi,nsis}/`. Les
installeurs ne sont **pas signés** : Windows SmartScreen affiche un avertissement au premier
lancement (signature : OPP-217).

Le dépôt force les fins de ligne **LF** (`.gitattributes`) : un checkout Windows ne casse
donc pas les scripts bash partagés avec WSL.

## Pièces

- `tauri.conf.json` — config : identifiant, icônes, `externalBin` (sidecar API),
  `resources` (arbre Ollama embarqué sous `ollama/`).
- `src/main.rs` — spawn des deux sidecars (Ollama puis API), attente de l'API,
  création de la fenêtre sur `http://127.0.0.1:8000`, arrêt des sidecars à la sortie.
  Sous Windows, les sidecars sont lancés avec `CREATE_NO_WINDOW` : aucune fenêtre console
  ne s'ouvre à côté de l'app (OPP-221).
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
