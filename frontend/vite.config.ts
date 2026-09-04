/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Proxy dev : les appels front sont préfixés par `/api` puis réécrits vers l'API Python
// (127.0.0.1:8000). Le préfixe évite le conflit avec les routes client React Router
// (ex. `/runs/:runId` est une route de page, pas un appel API).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        // Surchargée par API_PROXY_TARGET (ex. réseau Docker) ; défaut = API locale.
        target: process.env.API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.ts",
    css: false,
  },
});
