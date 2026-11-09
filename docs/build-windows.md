# Build Windows : recompiler le front et refaire les installeurs

Deux besoins distincts. Sauf mention contraire, les commandes se lancent depuis `frontend\`
(PowerShell).

## Prérequis (une seule fois)

Si `npm run build` échoue sur `Cannot find module '@tauri-apps/plugin-opener'` (ou
tout autre module), c'est que les dépendances ne sont pas installées :

```powershell
npm install
```

Pour les installeurs, il faut aussi :
- `rustc` dans le PATH (rustup) ;
- le venv Python `python\.venv` avec PyInstaller :
  `..\python\.venv\Scripts\python.exe -m pip install -e "..\python[build,scrape,pdf]"`.

## Cas 1 : voir la dernière version dans `python -m api.server`

Le serveur sert `frontend\dist`. S'il affiche une vieille version (ex. onglet
« Réglages » absent), c'est que `dist` est périmé. Il suffit de recompiler le front :

```powershell
npm run build
```

Puis relancer le serveur, depuis `python\` cette fois : `python -m api.server`.

## Cas 2 : refaire les installeurs `.exe` / `.msi`

L'installeur embarque le front compilé, le binaire API (sidecar PyInstaller) **et** un
Ollama CPU. Trois étapes :

```powershell
# A : télécharge Ollama, retire les runners GPU et dépose l'arbre CPU sous
#     src-tauri\binaries\ollama (ressource exigée par tauri.conf.json).
#     À refaire seulement si le dossier est absent ou pour changer de version.
pwsh -File src-tauri\sync-ollama.ps1

# B : reconstruit le sidecar API. Fait DÉJÀ "npm run build" en interne (front embarqué),
#     puis PyInstaller, puis dépose binaries\opportune-api-<triple>.exe que Tauri attend.
pwsh -File src-tauri\sync-sidecar.ps1

# C : fabrique les installeurs
npm run tauri build
```

Résultats (`targets: "all"` dans `tauri.conf.json` produit les deux sous Windows) :

```
frontend\src-tauri\target\release\bundle\msi\*.msi     (WiX)
frontend\src-tauri\target\release\bundle\nsis\*.exe    (NSIS)
```
