// Démarre l'API Python pour les tests de bout en bout (OPP-244).
//
// L'API sert aussi le front compilé (`frontend/dist`, cf. `api.frontend_assets`) : les tests
// tournent donc sur l'app telle qu'elle est livrée, à une seule adresse. Les bases SQLite et les
// réglages vont dans un dossier temporaire neuf (`OPPORTUNE_DATA_DIR`), effacé à l'arrêt : la démo
// y est seedée au démarrage, et les vraies données de la machine ne sont jamais touchées.
//
// Interpréteur Python : `OPPORTUNE_E2E_PYTHON` s'il est défini, sinon le venv du dépôt
// (`python/.venv`), sinon `python3` (CI, où le paquet est installé avec `pip install -e`).
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const pythonDir = resolve(frontendDir, "../python");

// Variables qui passent **avant** `OPPORTUNE_DATA_DIR` côté API : exportées dans le shell, elles
// feraient viser aux tests une vraie base (dont la démo, que chaque scénario restaure) ou un autre
// front compilé. On ne les transmet jamais.
const OVERRIDING_ENV = ["OPPORTUNE_DB_PATH", "OPPORTUNE_DEMO_DB_PATH", "OPPORTUNE_FRONTEND_DIST"];

function fail(message) {
  console.error(`[e2e] ${message}`);
  process.exit(1);
}

function pythonExecutable() {
  if (process.env.OPPORTUNE_E2E_PYTHON) return process.env.OPPORTUNE_E2E_PYTHON;
  const venvCandidates = [
    join(pythonDir, ".venv", "bin", "python"),
    join(pythonDir, ".venv", "Scripts", "python.exe"),
  ];
  return venvCandidates.find((candidate) => existsSync(candidate)) ?? "python3";
}

// Sans front compilé, l'API ne sert que `/api` : la page resterait blanche. On le dit tout de suite.
if (!existsSync(join(frontendDir, "dist", "index.html"))) {
  fail("front non compilé (frontend/dist absent) : lance `npm run test:e2e`, qui compile d'abord.");
}

const env = { ...process.env };
for (const key of OVERRIDING_ENV) delete env[key];
const dataDir = mkdtempSync(join(tmpdir(), "opportune-e2e-"));
const removeDataDir = () => rmSync(dataDir, { recursive: true, force: true });

const python = pythonExecutable();
const api = spawn(python, ["-m", "api.server"], {
  cwd: join(pythonDir, "src"),
  env: { ...env, OPPORTUNE_DATA_DIR: dataDir, PYTHONUNBUFFERED: "1" },
  stdio: "inherit",
});

// Interpréteur introuvable (ni venv, ni `python3`) : message clair au lieu d'une pile Node.
api.on("error", (error) => {
  removeDataDir();
  fail(`impossible de lancer l'API avec « ${python} » (${error.message}). Crée python/.venv ou `
    + "définis OPPORTUNE_E2E_PYTHON.");
});

// Playwright arrête ce script par SIGTERM à la fin des tests (`gracefulShutdown`) : on arrête
// l'API, puis on efface les données à sa sortie.
let stopping = false;
function stop() {
  stopping = true;
  api.kill("SIGTERM");
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
api.on("exit", (code, signal) => {
  removeDataDir();
  // Arrêt demandé : sortie normale. Sinon l'API s'est arrêtée seule, c'est un échec, même si
  // elle a été tuée par un signal (code `null`).
  if (stopping) process.exit(0);
  fail(`l'API s'est arrêtée d'elle-même (code ${code ?? "aucun"}, signal ${signal ?? "aucun"}).`);
});
