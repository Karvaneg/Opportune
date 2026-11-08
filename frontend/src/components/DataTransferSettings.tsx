import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useExportData } from "../api/dataTransfer";
import { useSpace } from "../space/SpaceContext";
import { ImportDataPicker } from "./ImportDataPicker";
import { ErrorNotice } from "./States";

/**
 * Sauvegarde des données (OPP-232) : exporter l'espace actif (« Mon espace » ou « Démo ») dans
 * un fichier, ou le remplacer par un export (changement d'ordinateur).
 */
export function DataTransferSettings() {
  const { space } = useSpace();
  const exportData = useExportData();
  const queryClient = useQueryClient();
  const [imported, setImported] = useState(false);

  const spaceName = space === "demo" ? "Démo" : "Mon espace";

  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface-raised p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
        Sauvegarde de mes données
      </h3>

      <div className="space-y-2 text-sm text-ink-muted">
        <p>
          L'export enregistre toutes les données de « {spaceName} » (recherches, profils, offres,
          analyses, lettres, candidatures et réglages) dans un fichier, à l'endroit de ton choix.
          Il contient aussi tes clés Adzuna : garde ce fichier pour toi.
        </p>
        <p>
          L'import remplace toutes les données actuelles de « {spaceName} » par celles d'un export,
          par exemple pour retrouver tes données sur un nouvel ordinateur.
        </p>
      </div>

      <div className="flex flex-wrap items-start gap-3">
        <button
          type="button"
          onClick={() => {
            setImported(false);
            exportData.mutate();
          }}
          disabled={exportData.isPending}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
        >
          {exportData.isPending ? "Export en cours…" : "Exporter mes données"}
        </button>
        <ImportDataPicker
          label="Importer des données"
          className="rounded-md border border-brand px-3 py-1.5 text-sm font-medium text-brand hover:bg-brand/10 disabled:opacity-50"
          onImported={() => {
            exportData.reset();
            setImported(true);
            // Toutes les données affichées viennent de changer : on rafraîchit tout.
            queryClient.invalidateQueries();
          }}
        />
      </div>

      {exportData.data?.saved &&
        (exportData.data.path ? (
          <p className="text-sm text-success-text">
            Données exportées dans : <code className="break-all">{exportData.data.path}</code>
          </p>
        ) : (
          <p className="text-sm text-success-text">Données exportées.</p>
        ))}
      {exportData.isError && <ErrorNotice error={exportData.error} />}
      {imported && <p className="text-sm text-success-text">Données importées.</p>}
    </div>
  );
}
