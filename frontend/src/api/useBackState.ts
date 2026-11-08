import { useLocation } from "react-router-dom";

/** État de navigation à passer à une fiche pour que son lien retour ramène ici (OPP-240). */
export interface BackState {
  /** Adresse de la page courante, paramètres compris (page, filtres). */
  from: string;
  /** L'origine de la page courante, rendue au retour pour que son propre retour marche aussi. */
  fromState: unknown;
}

/** Calcule l'état de retour vers la page courante (adresse complète + son origine). */
export function useBackState(): BackState {
  const location = useLocation();
  return { from: location.pathname + location.search, fromState: location.state };
}
