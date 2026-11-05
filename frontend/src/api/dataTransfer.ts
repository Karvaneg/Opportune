import { apiPost } from "./client";
import { useApiMutation } from "./mutations";
import { base64ToBytes } from "../lib/base64ToBytes";
import { saveZipFile } from "../lib/saveFile";

// Export / import des données de l'espace actif (OPP-232). Contrat miroir de `api.app`
// (routes POST /data/export et POST /data/import). L'API rend l'archive en base64 (transport
// JSON-only) ; le front l'enregistre là où l'utilisateur choisit. L'import envoie l'archive
// encodée en base64.

interface DataExportResponse {
  archive_base64: string;
  /** Nom proposé (ex. `opportune-export-2026-11-05.zip`). */
  filename: string;
}

/** Issue d'un export : chemin choisi (`""` si le navigateur ne le donne pas), ou annulé. */
export type DataExport = { saved: true; path: string } | { saved: false };

/** Taille max d'une archive acceptée côté front, alignée sur le back (200 Mo). */
export const MAX_ARCHIVE_BYTES = 200 * 1024 * 1024;

/** Envoie l'archive : remplace toutes les données de l'espace actif. */
export function importData(archiveBase64: string): Promise<{ status: string }> {
  return apiPost<{ status: string }>("/data/import", { archive_base64: archiveBase64 });
}

/** Récupère l'archive de l'espace actif puis l'enregistre à l'endroit choisi par l'utilisateur. */
export function useExportData() {
  return useApiMutation<DataExport, void>({
    mutationFn: async () => {
      const { archive_base64, filename } = await apiPost<DataExportResponse>("/data/export", {});
      const path = await saveZipFile(base64ToBytes(archive_base64), filename);
      return path === null ? { saved: false } : { saved: true, path };
    },
  });
}
