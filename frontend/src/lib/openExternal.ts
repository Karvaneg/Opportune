import { openUrl } from "@tauri-apps/plugin-opener";

/**
 * Ouvre une URL dans le navigateur système.
 *
 * L'app desktop charge le front dans une webview Tauri. Un `<a target="_blank">` y tente d'ouvrir
 * une popup que la webview WebKitGTK ne sait pas afficher (sous Linux : warning Gdk « Tried to map
 * a popup with a non-top most parent »), et le lien n'atteint jamais le navigateur. On délègue donc
 * au plugin opener, qui passe par le système.
 *
 * Hors Tauri (front servi dans un vrai navigateur, ex. `npm run dev` sur :5173), `openUrl` n'a pas
 * d'IPC à joindre : on retombe sur l'ouverture d'onglet classique. La présence de Tauri se détecte
 * par `__TAURI_INTERNALS__`, injecté dans toute webview Tauri même quand `withGlobalTauri` est à false.
 */
export async function openExternal(url: string): Promise<void> {
  if ("__TAURI_INTERNALS__" in window) {
    await openUrl(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}
