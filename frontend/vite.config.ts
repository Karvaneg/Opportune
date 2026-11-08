/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Proxy dev : les appels front sont préfixés par `/api` et transmis **tels quels** à l'API
// Python (127.0.0.1:8000), qui retire elle-même le préfixe avant dispatch (cf.
// `_strip_api_prefix` dans server.py). On ne réécrit donc PAS ici : le routage est alors
// identique en dev (via ce proxy) et en packagé (navigateur → API directe), où l'API
// distingue `/api/*` (données) du reste (front statique). Le préfixe évite le conflit avec
// les routes client React Router (ex. `/runs/:runId` est une route de page, pas un appel API).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Port fixe (OPP-233) : l'API n'accepte les écritures du front de dev que depuis :5173.
    // Si le port est pris, Vite s'arrête avec une erreur au lieu de basculer sur 5174, où
    // toutes les écritures recevraient un 403.
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        // Surchargée par API_PROXY_TARGET (ex. réseau Docker) ; défaut = API locale.
        target: process.env.API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  // `npm run preview` réutilise le proxy `/api` ci-dessus. Port fixe pour la même raison
  // (OPP-233) : l'API n'accepte les écritures de la prévisualisation que depuis :4173.
  preview: {
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
    css: false,
    // Les scénarios Playwright (`e2e/`, OPP-244) tournent à part, dans un vrai navigateur.
    include: ["tests/**/*.test.{ts,tsx}"],
  },
});
