import { apiPost } from "./client";
import { useApiMutation } from "./mutations";
import type { OfferSummary } from "./types";

export interface AddOfferVariables {
  /** Texte brut de l'offre (obligatoire côté back). */
  text: string;
  /** Provenance (défaut « collée » côté back). */
  source?: string;
  /** URL d'origine, purement informative à ce stade (le scraping est OPP-148). */
  url?: string;
}

/**
 * Ajoute une offre en collant son texte : `POST /offers` (OPP-145). Le back l'analyse via
 * LLM puis la persiste (id dérivé du texte → pas de doublon). Latence LLM → l'appelant gère
 * l'état d'attente. Erreurs remontées telles quelles (400 saisie, 502 analyse/LLM).
 */
export function useAddOffer() {
  return useApiMutation<OfferSummary, AddOfferVariables>({
    mutationFn: (variables, token) => apiPost<OfferSummary>("/offers", token, variables),
  });
}
