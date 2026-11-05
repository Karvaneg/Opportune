import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPut } from "./client";
import { useApiMutation } from "./mutations";
import { useIsReviewer } from "../auth/roles";

// Réglages de l'app (OPP-222). Pour l'instant : les identifiants Adzuna saisis par l'utilisateur.
// Contrat miroir de `api.app` (route /settings/adzuna). Les clés sont des **secrets** : l'API ne
// renvoie jamais que l'état « configuré », jamais les valeurs — le front ne les relit donc pas.

export interface AdzunaSettings {
  /** Des identifiants Adzuna exploitables sont-ils enregistrés ? (jamais les clés elles-mêmes). */
  configured: boolean;
}

export interface RssSettings {
  /** URLs des flux RSS saisies par l'utilisateur (non secrètes : relues telles quelles). */
  feeds: string[];
}

/** Entreprise ciblée sur un ATS (OPP-226), telle que l'API la rend. */
export interface AtsCompany {
  /** URL canonique de la page carrière, réaffichée dans le champ. */
  url: string;
  ats: "greenhouse" | "lever";
  slug: string;
  /** Offres en France, connu seulement juste après la vérification d'une nouvelle entreprise. */
  offers_in_france: number | null;
}

export interface AtsSettings {
  companies: AtsCompany[];
}

export const settingsKeys = {
  adzuna: ["settings", "adzuna"] as const,
  rss: ["settings", "rss"] as const,
  ats: ["settings", "ats"] as const,
};

/**
 * État des identifiants Adzuna : `GET /settings/adzuna` → `{ configured }` (jamais les clés).
 *
 * Réservé au reviewer côté back (403 sinon) : on conditionne donc la requête au rôle (`enabled`)
 * pour ne pas déclencher d'appel voué au 403 (et ses retries) chez un simple viewer.
 */
export function useAdzunaSettings() {
  const isReviewer = useIsReviewer();
  return useQuery({
    queryKey: settingsKeys.adzuna,
    queryFn: () => apiFetch<AdzunaSettings>("/settings/adzuna"),
    enabled: isReviewer,
  });
}

export interface SaveAdzunaVariables {
  appId: string;
  appKey: string;
}

/**
 * Enregistre les identifiants Adzuna : `PUT /settings/adzuna` (OPP-222). Reviewer uniquement
 * (saisie de secrets = curation). Au succès, invalide l'état `configured` pour le relire. Les
 * clés voyagent dans le corps mais ne sont jamais relues depuis l'API ensuite.
 */
export function useSaveAdzunaSettings() {
  return useApiMutation<AdzunaSettings, SaveAdzunaVariables>({
    mutationFn: ({ appId, appKey }) =>
      apiPut<AdzunaSettings>("/settings/adzuna", { app_id: appId, app_key: appKey }),
    invalidateKeys: () => [settingsKeys.adzuna],
  });
}

/**
 * URLs des flux RSS enregistrées : `GET /settings/rss` → `{ feeds }`. Réservé au reviewer côté
 * back (403 sinon) : on conditionne donc la requête au rôle (`enabled`), comme pour Adzuna.
 */
export function useRssSettings() {
  const isReviewer = useIsReviewer();
  return useQuery({
    queryKey: settingsKeys.rss,
    queryFn: () => apiFetch<RssSettings>("/settings/rss"),
    enabled: isReviewer,
  });
}

export interface SaveRssVariables {
  feeds: string[];
}

/**
 * Entreprises ciblées enregistrées : `GET /settings/ats` → `{ companies }` (OPP-226). Réservé au
 * reviewer côté back : requête conditionnée au rôle, comme pour les flux RSS.
 */
export function useAtsSettings() {
  const isReviewer = useIsReviewer();
  return useQuery({
    queryKey: settingsKeys.ats,
    queryFn: () => apiFetch<AtsSettings>("/settings/ats"),
    enabled: isReviewer,
  });
}

export interface SaveAtsVariables {
  /** URLs de pages carrière, une par entreprise (vide = tout supprimer). */
  companies: string[];
}

/**
 * Enregistre les entreprises ciblées : `PUT /settings/ats` (OPP-226). Le back vérifie chaque
 * nouvelle entreprise auprès de son ATS (400 si URL non reconnue ou entreprise introuvable, 502
 * si l'ATS est injoignable) et rend la liste retenue. Au succès, invalide l'état pour le relire.
 */
export function useSaveAtsSettings() {
  return useApiMutation<AtsSettings, SaveAtsVariables>({
    mutationFn: ({ companies }) => apiPut<AtsSettings>("/settings/ats", { companies }),
    invalidateKeys: () => [settingsKeys.ats],
  });
}

/**
 * Enregistre les URLs de flux RSS : `PUT /settings/rss` (OPP-195). Reviewer uniquement. Le back
 * ne retient que les URLs `http(s)` exploitables et renvoie la liste réellement enregistrée. Au
 * succès, invalide l'état pour le relire.
 */
export function useSaveRssSettings() {
  return useApiMutation<RssSettings, SaveRssVariables>({
    mutationFn: ({ feeds }) => apiPut<RssSettings>("/settings/rss", { feeds }),
    invalidateKeys: () => [settingsKeys.rss],
  });
}
