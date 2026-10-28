# Opportune — coquille desktop (Tauri, OPP-192)

Transforme les deux processus de dev (API Python + front Vite) en **une app de
bureau**. Tauri ne porte aucune logique métier : il lance le binaire API
(`opportune-api`, OPP-190) en **sidecar**, attend qu'il serve le front compilé
(OPP-191) sur `127.0.0.1:8000`, ouvre une fenêtre dessus, et arrête le sidecar à
la fermeture. Front et données viennent du même origin (le sidecar) : aucun CORS.

## Lancer en dev

Prérequis : Rust (`rustup`), le toolchain système Tauri, et Node. Sous WSL, la
fenêtre s'affiche via WSLg (`echo $DISPLAY` doit renvoyer `:0`).

```bash
cd frontend
npm install                      # récupère @tauri-apps/cli
bash src-tauri/sync-sidecar.sh   # construit front + binaire API, place le sidecar
npm run tauri dev                # compile la coquille Rust et ouvre la fenêtre
```

La **première** compilation Rust télécharge et bâtit les dépendances (plusieurs
minutes). Les suivantes sont rapides.

## Pièces

- `tauri.conf.json` — config : identifiant, icônes, `externalBin` (le sidecar).
- `src/main.rs` — spawn du sidecar, attente de disponibilité, création de la
  fenêtre sur `http://127.0.0.1:8000`, arrêt du sidecar à la fermeture.
- `sync-sidecar.sh` — copie le binaire API sous `binaries/opportune-api-<triple>`,
  nom où Tauri résout son sidecar.
- `binaries/`, `target/`, `gen/` — artefacts de build, non versionnés.

## Limites connues (socle 1.0)

- **Port figé 8000** : si le port est déjà pris (p. ex. un serveur de dev), le
  sidecar ne démarre pas. Un port dynamique viendra si besoin.
- **Icônes** : placeholders 32×32. Le jeu multi-résolutions (`.ico`/`.icns`)
  arrive avec les installeurs signés (OPP-194).
- **Build Windows/Mac** : fait sur ces OS / en CI (OPP-194), pas en cross-compile.
- **Message d'échec invisible sur Windows release** : si le sidecar ne démarre pas,
  l'erreur part sur `eprintln!`, sans console en release (`windows_subsystem =
  "windows"`). Un vrai dialogue d'erreur (tauri-plugin-dialog) relève de l'onboarding
  1er lancement (OPP-195).
