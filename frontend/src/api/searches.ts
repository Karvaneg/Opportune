import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPut } from "./client";
import { useApiMutation } from "./mutations";
import type { Search, SearchesResponse } from "./types";

/**
 * Recherches de l'espace (le périmètre, OPP-184). Clé unique : la liste ne dépend que de
 * l'espace actif (porté par l'en-tête `X-Opportune-Space`, hors clé de cache car le cache est
 * déjà remonté à zéro au changement d'espace, cf. App). Création / renommage invalident cette clé.
 */
export const searchKeys = {
  all: ["searches"] as const,
};

/**
 * Liste des recherches de l'espace : `GET /searches` (OPP-184). Source réactive du périmètre
 * (ids + libellés) — alimente le sélecteur global et, via `useTargetCandidate`, la recherche
 * active partagée par toutes les pages. Une recherche créée apparaît dès l'invalidation.
 */
export function useSearches() {
  return useQuery({
    queryKey: searchKeys.all,
    queryFn: () => apiFetch<SearchesResponse>("/searches"),
  });
}

/**
 * Crée une recherche nommée : `POST /searches` (OPP-184). Reviewer uniquement (modifier le
 * périmètre, comme la curation d'offres). Le back génère l'id technique ; au succès on invalide
 * la liste (la nouvelle recherche apparaît) — l'appelant bascule dessus via l'id renvoyé.
 */
export function useCreateSearch() {
  return useApiMutation<Search, string>({
    mutationFn: (label) => apiPost<Search>("/searches", { label }),
    invalidateKeys: () => [searchKeys.all],
  });
}

export interface RenameSearchVariables {
  id: string;
  label: string;
}

/**
 * Renomme une recherche : `PUT /searches/{id}` (OPP-184). Reviewer uniquement. 404 neutre si l'id
 * est hors périmètre (anti-énumération, remonté comme `ApiHttpError`). Invalide la liste au succès.
 */
export function useRenameSearch() {
  return useApiMutation<Search, RenameSearchVariables>({
    mutationFn: ({ id, label }) =>
      apiPut<Search>(`/searches/${encodeURIComponent(id)}`, { label }),
    invalidateKeys: () => [searchKeys.all],
  });
}
