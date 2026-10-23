import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { resetDemo, restoreDemo } from "../api/demo";

/**
 * Bandeau de l'espace démo (OPP-182) : rappelle qu'on est dans un bac à sable isolé et offre de
 * **repartir de zéro** (vider → refaire le parcours à la main) ou de **restaurer l'exemple** (la
 * vitrine pré-remplie). Après l'action, on invalide tout le cache pour que les pages reflètent
 * le nouvel état de la base démo. N'est rendu que dans l'espace démo (cf. `App`).
 */
export function DemoBanner() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>, confirmMessage?: string) {
    if (confirmMessage && !window.confirm(confirmMessage)) return;
    setBusy(true);
    setError(null);
    try {
      await action();
      // `resetQueries` (et non `invalidateQueries`) : après un reset, le profil démo est
      // supprimé → `GET …/profile` renvoie 404, et React Query **conserverait la donnée
      // précédente** sur erreur de refetch (le guide verrait alors un profil fantôme et
      // barrerait « Ajouter votre CV » à tort). `resetQueries` purge le cache puis refetch —
      // même état neuf qu'un changement d'espace.
      await queryClient.resetQueries();
    } catch {
      // En cas d'échec (réseau, 500) la base démo n'a pas bougé (commande transactionnelle
      // côté back) : on le signale plutôt que de laisser l'action échouer en silence.
      setError("L'action a échoué. Réessaie dans un instant.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-b border-amber-200 bg-amber-50">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm sm:px-6">
        <span className={error ? "text-red-700" : "text-amber-800"}>
          {error ??
            "Espace démo — un bac à sable isolé, tes vraies données n'y sont jamais touchées."}
        </span>
        <div className="flex items-center gap-2">
          <button
            disabled={busy}
            onClick={() =>
              run(resetDemo, "Vider la démo pour repartir de zéro ? Les données d'exemple seront effacées.")
            }
            className="rounded-md px-2 py-1 font-medium text-amber-800 transition-colors hover:bg-amber-100 disabled:opacity-50"
          >
            Repartir de zéro
          </button>
          <button
            disabled={busy}
            onClick={() => run(restoreDemo)}
            className="rounded-md px-2 py-1 font-medium text-amber-800 transition-colors hover:bg-amber-100 disabled:opacity-50"
          >
            Restaurer l'exemple
          </button>
        </div>
      </div>
    </div>
  );
}
