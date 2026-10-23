import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "./AuthContext";

/** Référence stable pour un périmètre vide : évite de recréer la valeur du contexte à chaque rendu. */
const NO_CANDIDATES: string[] = [];

type TargetCandidate = {
  candidates: string[];
  target: string;
  setCandidate: (next: string) => void;
};

const TargetCandidateContext = createContext<TargetCandidate | null>(null);

/**
 * Candidat ciblé par les pages du périmètre (accueil, profil, offres, lancement de run).
 * **Partagé via contexte** : la sélection suit la navigation d'une page à l'autre, au lieu que
 * chaque page reparte du 1er candidat (sinon choisir le candidat B sur l'accueil puis ouvrir
 * « Profil » retomberait sur A). `target` reprojette toujours la sélection sur une valeur
 * **réellement du périmètre** — si `identity` est re-fetchée et que la sélection en sort (ou si
 * elle n'a jamais été posée), on retombe sur le 1er candidat : un `<select>` lié à `target`
 * pointe donc toujours une `<option>` existante, et un POST cible un candidat du périmètre.
 * `target` vaut `""` quand le périmètre est vide.
 */
export function TargetCandidateProvider({ children }: { children: ReactNode }) {
  const { identity } = useAuth();
  const candidates = identity?.owned_candidate_ids ?? NO_CANDIDATES;
  const [candidate, setCandidate] = useState("");
  const target = candidates.includes(candidate) ? candidate : candidates[0] ?? "";
  const value = useMemo<TargetCandidate>(
    () => ({ candidates, target, setCandidate }),
    [candidates, target],
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
