import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useSearches } from "../api/searches";
import type { Search } from "../api/types";

/** Référence stable pour un périmètre vide : évite de recréer la valeur du contexte à chaque rendu. */
const NO_SEARCHES: Search[] = [];

type TargetCandidate = {
  /** Recherches du périmètre (id + libellé), source du sélecteur global (OPP-184). */
  searches: Search[];
  /** Ids seuls — ce que ciblent les requêtes (compat avec les pages et `LaunchRun`). */
  candidates: string[];
  target: string;
  setCandidate: (next: string) => void;
  /** `true` tant que `GET /searches` n'a pas répondu (périmètre indéterminé, pas encore « vide »). */
  isPending: boolean;
  /** `true` si `GET /searches` a échoué : un périmètre « vide » n'est alors pas fiable (API HS). */
  isError: boolean;
  /** Erreur de `GET /searches` (message déjà neutralisé par `apiFetch`), pour l'afficher. */
  error: unknown;
};

const TargetCandidateContext = createContext<TargetCandidate | null>(null);

/**
 * Recherche active ciblée par les pages du périmètre (accueil, profil, offres, lancement de run).
 * **Partagée via contexte** : la sélection suit la navigation d'une page à l'autre, au lieu que
 * chaque page reparte de la 1ʳᵉ recherche. La source est désormais `GET /searches` (OPP-184, via
 * React Query) plutôt que l'identité figée au boot : une recherche créée ou renommée se reflète
 * aussitôt, et les libellés sont disponibles. `target` reprojette toujours la sélection sur une
 * valeur **réellement du périmètre** — si la liste change et que la sélection en sort (ou n'a
 * jamais été posée), on retombe sur la 1ʳᵉ recherche : un `<select>` lié à `target` pointe donc
 * toujours une `<option>` existante, et un POST cible une recherche du périmètre. `target` vaut
 * `""` quand le périmètre est vide.
 */
export function TargetCandidateProvider({ children }: { children: ReactNode }) {
  const { data, isPending, isError, error } = useSearches();
  const searches = data?.items ?? NO_SEARCHES;
  const candidates = useMemo(() => searches.map((s) => s.id), [searches]);
  const [candidate, setCandidate] = useState("");
  const target = candidates.includes(candidate) ? candidate : candidates[0] ?? "";
  const value = useMemo<TargetCandidate>(
    () => ({ searches, candidates, target, setCandidate, isPending, isError, error }),
    [searches, candidates, target, isPending, isError, error],
  );
  return (
    <TargetCandidateContext.Provider value={value}>{children}</TargetCandidateContext.Provider>
  );
}

export function useTargetCandidate(): TargetCandidate {
  const ctx = useContext(TargetCandidateContext);
  if (!ctx) {
    throw new Error("useTargetCandidate doit être appelé dans un <TargetCandidateProvider>.");
  }
  return ctx;
}
