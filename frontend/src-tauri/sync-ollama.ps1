# Équivalent Windows de sync-ollama.sh (OPP-194) : embarque une version CPU seule d'Ollama
# pour le sidecar desktop. Les scripts bash (sync-ollama.sh) ne tournent pas sous Windows ;
# ce script fait la même chose avec les outils Windows (curl.exe, Expand-Archive).
#
# La release Windows officielle (ollama-windows-amd64.zip) embarque le runner CPU **et** les
# runners GPU (CUDA, ROCm, Vulkan). Pour un modèle 3B sur une machine de non-dev, le GPU est
# inutile : on télécharge le zip, on **jette** `lib\ollama\{cuda*,rocm*,vulkan*}` et on ne garde
# que `ollama.exe` + les libs CPU. L'arbre est déposé sous `binaries\ollama\` avec `ollama.exe` à
# la racine et `lib\ollama` voisin, exactement ce que `src\main.rs` (ollama_paths) attend sous
# Windows. Il est ensuite embarqué comme ressource Tauri (tauri.conf.json → bundle.resources).
#
# Usage (depuis frontend\src-tauri\ ou ailleurs) :
#   pwsh -File src-tauri\sync-ollama.ps1
#   $env:OLLAMA_VERSION = "v0.40.13"; pwsh -File src-tauri\sync-ollama.ps1
#
# Prérequis : curl.exe (fourni avec Windows 10+) et Expand-Archive (PowerShell 5+).

param(
    [string]$OllamaVersion = $(if ($env:OLLAMA_VERSION) { $env:OLLAMA_VERSION } else { "v0.40.13" })
)

$ErrorActionPreference = "Stop"

# Dossier de ce script (frontend\src-tauri), d'où l'on dérive la destination.
$TauriDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = Join-Path $TauriDir "binaries\ollama"

$Asset = "ollama-windows-amd64.zip"
$Url = "https://github.com/ollama/ollama/releases/download/$OllamaVersion/$Asset"

$Tmp = Join-Path $env:TEMP ("ollama-sync-" + [guid]::NewGuid().ToString("N"))
$Extracted = Join-Path $Tmp "extracted"
New-Item -ItemType Directory -Force $Extracted | Out-Null

try {
    $zip = Join-Path $Tmp $Asset
    Write-Host "→ Téléchargement d'Ollama $OllamaVersion ($Asset)…"
    # curl.exe suit les redirections GitHub ; --fail pour sortir en erreur sur un 404.
    curl.exe --fail --show-error --location --progress-bar -o $zip $Url
    if ($LASTEXITCODE -ne 0) { throw "Échec du téléchargement ($Url)." }

    Write-Host "→ Extraction…"
    Expand-Archive -Path $zip -DestinationPath $Extracted -Force

    # ollama.exe est à la racine du zip Windows ; on le localise pour valider la structure.
    $exe = Get-ChildItem -Path $Extracted -Recurse -Filter "ollama.exe" | Select-Object -First 1
    if (-not $exe) { throw "Structure inattendue : ollama.exe absent de l'archive." }
    $root = $exe.Directory.FullName

    # Élagage des runners GPU (CUDA / ROCm / Vulkan) sous lib\ollama.
    $lib = Join-Path $root "lib\ollama"
    if (Test-Path $lib) {
        Write-Host "→ Suppression des runners GPU (CUDA/ROCm/Vulkan)…"
        Get-ChildItem $lib -Directory |
            Where-Object { $_.Name -match '^(cuda|rocm|vulkan)' } |
            Remove-Item -Recurse -Force
        # Le runner Vulkan peut aussi être un fichier (DLL) directement sous lib\ollama.
        Get-ChildItem $lib -File |
            Where-Object { $_.Name -match 'vulkan' } |
            Remove-Item -Force
    }

    # Dépôt de l'arbre CPU : tout le contenu de la racine du zip (ollama.exe + lib, moins le GPU).
    if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
    New-Item -ItemType Directory -Force $Dest | Out-Null
    Copy-Item (Join-Path $root "*") $Dest -Recurse -Force

    $sizeMb = (Get-ChildItem $Dest -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host ("✓ Ollama CPU en place : {0} ({1:N0} Mo)" -f $Dest, $sizeMb)
}
finally {
    if (Test-Path $Tmp) { Remove-Item $Tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
