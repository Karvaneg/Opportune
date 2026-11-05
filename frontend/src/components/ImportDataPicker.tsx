import { useRef, useState, type ChangeEvent } from "react";
import { MAX_ARCHIVE_BYTES, importData } from "../api/dataTransfer";
import { fileToBase64 } from "../lib/fileToBase64";
import { useSpace, type Space } from "../space/SpaceContext";
import { ErrorNotice } from "./States";

/** Message de confirmation avant de remplacer les données de l'espace actif (OPP-232). */
export function importConfirmation(space: Space | null): string {
  const name = space === "demo" ? "Démo" : "Mon espace";
  return `Les données actuelles de « ${name} » seront remplacées par celles du fichier. Continuer ?`;
}

/**
 * Bouton « importer des données » (OPP-232) : choisit un fichier d'export, demande confirmation,
 * puis remplace les données de l'espace actif. Le parent décide quoi faire après l'import
 * (rafraîchir les données affichées).
 */
export function ImportDataPicker({
  label,
  className,
  onImported,
}: {
  label: string;
  className: string;
  onImported: () => void;
}) {
  const { space } = useSpace();
  const input = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Remet le champ à zéro : choisir de nouveau le même fichier relancera l'import.
    event.target.value = "";
    if (!file) return;
    setError(null);
    if (file.size > MAX_ARCHIVE_BYTES) {
      setError(new Error("Le fichier dépasse la taille maximale d'un export (200 Mo)."));
      return;
    }
    if (!window.confirm(importConfirmation(space))) return;
    setImporting(true);
    try {
      await importData(await fileToBase64(file));
      onImported();
    } catch (caught) {
      setError(caught);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="space-y-2">
      <input
        ref={input}
        type="file"
        accept=".zip,application/zip"
        onChange={onFile}
        className="hidden"
        aria-label="Fichier d'export Opportune"
      />
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={importing}
        className={className}
      >
        {importing ? "Import en cours…" : label}
      </button>
      {error !== null && <ErrorNotice error={error} />}
    </div>
  );
}
