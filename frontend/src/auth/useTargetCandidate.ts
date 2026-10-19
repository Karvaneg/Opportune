import { useState } from "react";
import { useAuth } from "./AuthContext";

/**
 * Candidat ciblé par une page du périmètre (cockpit, offres, lancement de run). Factorise un
 * pattern répété : l'état `candidate` est figé au montage, mais `target` le reprojette toujours
 * sur une valeur **réellement du périmètre** — si `identity` est re-fetchée et que la sélection
 * en sort (ou si elle était vide au montage), on retombe sur le 1er candidat. Garantit qu'un
 * `<select>` lié à `target` pointe toujours une `<option>` existante et qu'un POST cible un
 * candidat du périmètre.
 *
 * `initial` dérive la valeur de départ des candidats connus au montage (p. ex. un `?candidate=`
 * d'URL) ; par défaut, le 1er du périmètre. `target` vaut `""` quand le périmètre est vide.
 */
export function useTargetCandidate(initial?: (candidates: string[]) => string) {
  const { identity } = useAuth();
  const candidates = identity?.owned_candidate_ids ?? [];
  const [candidate, setCandidate] = useState(() =>
    initial ? initial(candidates) : candidates[0] ?? "",
  );
  const target = candidates.includes(candidate) ? candidate : candidates[0] ?? "";
  return { candidates, target, setCandidate };
}
