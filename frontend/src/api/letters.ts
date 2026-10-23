import { useQuery } from "@tanstack/react-query";
import { apiDelete, apiFetch, apiPost, apiPut } from "./client";
import { useApiMutation } from "./mutations";
import type { Letter } from "./types";

// Clé de cache de la lettre d'une reco. Indexée par recommendation_id (une lettre par reco).
export const letterKeys = {
  detail: (recommendationId: string) => ["letter", recommendationId] as const,
};

/**
 * Lettre d'une recommandation : `GET /recommendations/{id}/letter` (OPP-147).
 * `retry: false` — un 404 signifie « pas encore de lettre » (état normal, pas une panne) :
 * l'appelant distingue ce 404 d'une vraie erreur pour proposer la génération.
 */
export function useLetter(recommendationId: string) {
  return useQuery({
    queryKey: letterKeys.detail(recommendationId),
    queryFn: () =>
      apiFetch<Letter>(
        `/recommendations/${encodeURIComponent(recommendationId)}/letter`,
      ),
    enabled: recommendationId.length > 0,
    retry: false,
  });
}

/**
 * Génère (ou régénère) la lettre : `POST /recommendations/{id}/letter` (OPP-147).
 * Sans lettre existante → `{}` (201). Pour écraser une lettre existante (y compris éditée),
 * la variable porte `{ regenerate: true }` — geste explicite de l'humain après le 409 que
 * renvoie le back sur une régénération non confirmée. Au succès, invalide la lettre en cache.
 */
export function useGenerateLetter(recommendationId: string) {
  return useApiMutation<Letter, { regenerate?: boolean }>({
    mutationFn: (variables) =>
      apiPost<Letter>(
        `/recommendations/${encodeURIComponent(recommendationId)}/letter`,
        variables ?? {},
      ),
    invalidateKeys: () => [letterKeys.detail(recommendationId)],
  });
}

/**
 * Édite le corps de la lettre : `PUT /recommendations/{id}/letter` (OPP-147). Variable = le
 * nouveau corps ; le back bascule la provenance en `human`. Invalide la lettre en cache.
 */
export function useEditLetter(recommendationId: string) {
  return useApiMutation<Letter, string>({
    mutationFn: (body) =>
      apiPut<Letter>(
        `/recommendations/${encodeURIComponent(recommendationId)}/letter`,
        { body },
      ),
    invalidateKeys: () => [letterKeys.detail(recommendationId)],
  });
}

/**
 * Supprime la lettre : `DELETE /recommendations/{id}/letter` (OPP-147). Au succès, invalide
 * la lettre en cache → le panneau repasse à l'état « aucune lettre ».
 */
export function useDeleteLetter(recommendationId: string) {
  return useApiMutation<{ deleted: string }, void>({
    mutationFn: (_variables) =>
      apiDelete<{ deleted: string }>(
        `/recommendations/${encodeURIComponent(recommendationId)}/letter`,
      ),
    invalidateKeys: () => [letterKeys.detail(recommendationId)],
  });
}
