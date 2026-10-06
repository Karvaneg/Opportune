import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";
import type { OffersCatalogPage, OfferSummary } from "./types";

// Clé de cache du catalogue : page + candidat ciblé (chaque combinaison a son cache).
export const offerKeys = {
  catalog: (page: number, candidateId: string) => ["offers", page, candidateId] as const,
};

/**
 * Catalogue paginé des offres : `GET /offers` (OPP-146). `candidateId` (optionnel) annote
 * chaque offre de son score de match pour ce candidat ; vide = catalogue brut (scores
 * `null`). Plus récentes d'abord (tri serveur, OPP-152).
 */
export function useOffers(page: number, candidateId: string) {
  const { token } = useAuth();
  const params = new URLSearchParams({ page: String(page) });
  if (candidateId) params.set("candidate_id", candidateId);
  return useQuery({
    queryKey: offerKeys.catalog(page, candidateId),
    queryFn: () => apiFetch<OffersCatalogPage>(`/offers?${params}`, token!),
    enabled: Boolean(token),
    placeholderData: keepPreviousData, // évite le clignotement entre pages/candidats
  });
}

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
