import { defineConfig, devices } from "@playwright/test";

// Tests de bout en bout sur l'espace Démo (OPP-244) : un vrai navigateur sur le front compilé,
// servi par la vraie API Python (cf. `e2e/start-api.mjs`). Lancer avec `npm run test:e2e`, qui
// compile le front d'abord (`vite build` seul : le typage est vérifié par `npm run lint`).
// L'API sert `frontend/dist`.

// Port réservé aux tests, distinct de celui de l'app (8000) et du front de dev (5173). L'API
// accepte les écritures venant de sa propre origine : la page et l'API partagent ce port.
const PORT = 8765;
const baseURL = `http://127.0.0.1:${PORT}`;

// Ralenti facultatif pour suivre les scénarios à l'œil : `E2E_SLOWMO=500 npm run test:e2e --
// --headed` attend 500 ms entre chaque action. Absent ou invalide : aucune pause.
const slowMo = Number(process.env.E2E_SLOWMO) || 0;

export default defineConfig({
  testDir: "./e2e",
  // Une seule base démo pour toute la passe : les scénarios la restaurent un par un, donc ils
  // ne peuvent pas tourner en parallèle.
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    launchOptions: { slowMo },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node e2e/start-api.mjs",
    // Route d'API, pas `/` : la disponibilité de l'API ne dépend pas du front compilé (dont
    // l'absence est signalée tout de suite par `start-api.mjs`).
    url: `${baseURL}/api/me`,
    env: { OPPORTUNE_API_PORT: String(PORT) },
    // Jamais une API déjà lancée : elle pourrait viser d'autres données que la base temporaire.
    reuseExistingServer: false,
    timeout: 60_000,
    // SIGTERM plutôt qu'un arrêt brutal : `start-api.mjs` arrête alors l'API et efface le
    // dossier temporaire des données.
    gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
  },
});
