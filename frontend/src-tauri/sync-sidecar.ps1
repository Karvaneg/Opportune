# Équivalent Windows de sync-sidecar.sh + build-api.sh (OPP-194) : construit le binaire API
# autonome (PyInstaller) et le place là où Tauri attend son sidecar. Les scripts bash
# (sync-sidecar.sh, build-api.sh) ne tournent pas sous Windows ; ce script fait la même chose
# avec les outils Windows. PyInstaller ne fait **pas** de cross-compilation : lancer ce script
# sous Windows produit bien le binaire Windows.
#
# Ce qu'il fait, dans l'ordre :
#   1. (re)construit le front (`npm run build`) — embarqué dans le binaire (OPP-191) ;
#   2. construit le binaire autonome via le spec PyInstaller (OPP-190) ;
#   3. le copie sous `binaries\opportune-api-<triple>.exe`, nom que Tauri résout (OPP-192).
#
# Usage (depuis frontend\src-tauri\ ou ailleurs) :
#   pwsh -File src-tauri\sync-sidecar.ps1
#
# Prérequis : rustc (pour connaître le triple cible), Node/npm (build front), et un Python
# avec l'extra `build` installé (PyInstaller) :
#   py -m venv python\.venv ; python\.venv\Scripts\python.exe -m pip install -e "python\[build,scrape,pdf]"

$ErrorActionPreference = "Stop"

$TauriDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $TauriDir "..\..")
$PyDir = Join-Path $RepoRoot "python"
$FrontendDir = Join-Path $RepoRoot "frontend"

# --- Triple de la cible courante, tel que Tauri le nomme (ex. x86_64-pc-windows-msvc) -------
if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
    throw "rustc introuvable : installe Rust (rustup) d'abord."
}
$triple = ((rustc -vV) | Select-String '^host:').ToString().Split()[1]

# --- Front compilé embarqué dans le binaire (OPP-191) : on le (re)construit d'abord ---------
Write-Host "→ Construction du front (npm run build)…"
Push-Location $FrontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build a échoué." }
}
finally { Pop-Location }

# --- Interpréteur Python : venv local d'abord, puis venv activé, puis python du PATH ---------
$venvPy = Join-Path $PyDir ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $python = $venvPy
}
elseif ($env:VIRTUAL_ENV -and (Test-Path (Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"))) {
    $python = Join-Path $env:VIRTUAL_ENV "Scripts\python.exe"
}
else {
    $python = "python"
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller introuvable pour $python. Installer l'extra build : & '$python' -m pip install -e '.[build,scrape,pdf]' (depuis python\)"
}

# --- Construction du binaire (PyInstaller) --------------------------------------------------
Write-Host "→ Construction du binaire (PyInstaller)…"
Push-Location $PyDir
try {
    & $python -m PyInstaller --clean --noconfirm packaging/opportune-api.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué." }
}
finally { Pop-Location }

# --- Dépôt du sidecar sous le nom attendu par Tauri -----------------------------------------
$src = Join-Path $PyDir "dist\opportune-api.exe"
if (-not (Test-Path $src)) { throw "Binaire attendu introuvable : $src" }

$binDir = Join-Path $TauriDir "binaries"
New-Item -ItemType Directory -Force $binDir | Out-Null
$dest = Join-Path $binDir "opportune-api-$triple.exe"
Copy-Item $src $dest -Force

Write-Host "✓ Sidecar en place : $dest"
