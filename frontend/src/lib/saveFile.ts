import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";

/** Fenêtre « Enregistrer sous » des navigateurs Chromium (File System Access API), absente des
 * types DOM standard et de Firefox / Safari. */
type SaveFilePicker = (options: {
  suggestedName: string;
  types: Array<{ description: string; accept: Record<string, string[]> }>;
}) => Promise<{ createWritable: () => Promise<{ write: (data: Blob) => Promise<void>; close: () => Promise<void> }> }>;

/** L'utilisateur a fermé la fenêtre « Enregistrer sous » sans choisir d'emplacement. */
const CANCELLED = null;

/**
 * Enregistre un fichier `.zip` à l'endroit choisi par l'utilisateur (OPP-232).
 *
 * Rend le chemin choisi quand il est connu (app de bureau), `""` quand le navigateur ne le donne
 * pas, et `null` si l'utilisateur annule.
 *
 * - **App de bureau (Tauri)** : fenêtre « Enregistrer sous » du système (plugin dialog), puis
 *   écriture par le plugin fs. Le plugin dialog n'autorise l'écriture que sur le chemin choisi.
 * - **Navigateur Chromium** : fenêtre « Enregistrer sous » du navigateur (`showSaveFilePicker`).
 * - **Autres navigateurs** : téléchargement classique ; l'emplacement dépend des réglages du
 *   navigateur (certains demandent où enregistrer).
 */
export async function saveZipFile(content: Uint8Array, filename: string): Promise<string | null> {
  if ("__TAURI_INTERNALS__" in window) {
    const path = await save({
      defaultPath: filename,
      filters: [{ name: "Archive zip", extensions: ["zip"] }],
    });
    if (path === null) return CANCELLED;
    await writeFile(path, content);
    return path;
  }

  const blob = new Blob([content as BlobPart], { type: "application/zip" });
  const picker = (window as unknown as { showSaveFilePicker?: SaveFilePicker }).showSaveFilePicker;
  if (picker) {
    try {
      const handle = await picker({
        suggestedName: filename,
        types: [{ description: "Archive zip", accept: { "application/zip": [".zip"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return "";
    } catch (error) {
      // Fenêtre fermée sans choisir : le navigateur lève une AbortError.
      if (error instanceof DOMException && error.name === "AbortError") return CANCELLED;
      throw error;
    }
  }

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  // Firefox et Safari démarrent le téléchargement après coup : révoquer l'URL tout de suite
  // l'interromprait. On laisse au navigateur le temps de la lire.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return "";
}

