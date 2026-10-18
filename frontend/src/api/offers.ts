import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";
import type { OffersCatalogPage, OfferSummary, RecommendationDetail } from "./types";

// Clé de cache du catalogue : page + candidat ciblé (chaque combinaison a son cache).
// `all` est le préfixe commun (invalidation de toutes les pages/candidats, cf. `useAddOffer`).
export const offerKeys = {
  all: ["offers"] as const,
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
  /** Texte brut de l'offre. Fournir `text` OU `url` (le texte prime si les deux sont là). */
  text?: string;
  /** URL de l'offre : le back récupère la page et en extrait le texte (OPP-148). */
  url?: string;
  /** Provenance (défaut « collée » pour le texte, le domaine pour une URL). */
  source?: string;
}

/**
 * Ajoute une offre, par texte collé (OPP-145) ou par URL (OPP-148) : `POST /offers`. Le back
 * analyse via LLM puis persiste (id dérivé du texte → pas de doublon). Latence LLM (+ fetch
 * pour une URL) → l'appelant gère l'attente. Erreurs remontées telles quelles : 400 (saisie
 * ou URL refusée/SSRF), 502 (analyse/LLM, ou récupération de l'URL impossible). Au succès,
 * invalide le catalogue (préfixe `["offers"]`, toutes pages/candidats) pour que la nouvelle
 * offre y apparaisse sans rechargement (OPP-161).
 */
export function useAddOffer() {
  return useApiMutation<OfferSummary, AddOfferVariables>({
    mutationFn: (variables, token) => apiPost<OfferSummary>("/offers", token, variables),
    invalidateKeys: () => [offerKeys.all],
  });
}

export interface EvaluateOfferVariables {
  candidateId: string;
  offerId: string;
}

/**
 * Ouvre la fiche d'une offre pour un candidat depuis le catalogue (OPP-160) : `POST
 * /candidates/{cid}/offers/{oid}/rescore`. Get-or-create — garantit qu'une décision existe
 * (score + décision `pending` créés si l'offre n'avait jamais été évaluée), **sans créer de
 * run**, et préserve une décision humaine déjà prise. Retourne le détail de la recommandation
 * (dont `recommendation_id`) vers lequel l'appelant navigue.
 *
 * Même route que `useRescoreOffer` (OPP-150, recommendations.ts) : garder les deux synchronisés
 * si le contrat bouge. La divergence est volontaire — ici pas de reco préexistante à invalider,
 * donc pas d'`invalidateKeys` (le catalogue se refetch au remontage de la page).
 */
export function useEvaluateOffer() {
  return useApiMutation<RecommendationDetail, EvaluateOfferVariables>({
    mutationFn: ({ candidateId, offerId }, token) =>
      apiPost<RecommendationDetail>(
        `/candidates/${encodeURIComponent(candidateId)}/offers/${encodeURIComponent(offerId)}/rescore`,
        token,
        {},
      ),
  });
}
