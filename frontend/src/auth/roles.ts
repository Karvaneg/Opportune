import type { Me } from "../api/types";
import { useAuth } from "./AuthContext";

// Rôle habilité aux actions métier (validation, candidature…). Miroir côté front de
// REVIEWER de l'API : la garde UI est une défense en profondeur, le back conserve le 403.
export const REVIEWER_ROLE = "reviewer";

/** Vrai si l'identité porte le rôle reviewer. Fonction pure → directement testable. */
export function isReviewer(identity: Me | null): boolean {
  return identity?.role === REVIEWER_ROLE;
}

/** Commodité : dérive `isReviewer` de l'identité courante du contexte d'auth (OPP-106). */
export function useIsReviewer(): boolean {
  return isReviewer(useAuth().identity);
}
