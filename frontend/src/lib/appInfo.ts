/**
 * Informations sur l'application, affichées dans « À propos » et au pied de l'écran d'accueil
 * (OPP-246).
 *
 * La version vient de `frontend/package.json`, injectée au build par Vite (`__APP_VERSION__`,
 * cf. `vite.config.ts`). L'app de bureau la lit aussi (`tauri.conf.json` pointe vers ce fichier).
 * `python/pyproject.toml`, `python/src/app/__init__.py` et `src-tauri/Cargo.toml` la répètent :
 * `python/tests/test_version_alignment.py` échoue si l'un d'eux diverge.
 */
export const APP_INFO = {
  name: "Opportune",
  version: __APP_VERSION__,
  author: "Marie Le Carvennec",
  // Année de création, celle du copyright du fichier LICENSE.
  year: 2026,
  license: "MIT",
  licenseUrl: "https://github.com/Karvaneg/Opportune/blob/main/LICENSE",
  authorUrl: "https://github.com/Karvaneg",
  repoUrl: "https://github.com/Karvaneg/Opportune",
} as const;
