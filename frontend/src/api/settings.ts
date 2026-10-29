import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPut } from "./client";
import { useApiMutation } from "./mutations";

// Réglages de l'app (OPP-222). Pour l'instant : les identifiants Adzuna saisis par l'utilisateur.
// Contrat miroir de `api.app` (route /settings/adzuna). Les clés sont des **secrets** : l'API ne
// renvoie jamais que l'état « configuré », jamais les valeurs — le front ne les relit donc pas.

export interface AdzunaSettings {
  /** Des identifiants Adzuna exploitables sont-ils enregistrés ? (jamais les clés elles-mêmes). */
  configured: boolean;
}

export const settingsKeys = {
  adzuna: ["settings", "adzuna"] as const,
};

/** État des identifiants Adzuna : `GET /settings/adzuna` → `{ configured }` (jamais les clés). */
export function useAdzunaSettings() {
  return useQuery({
    queryKey: settingsKeys.adzuna,
    queryFn: () => apiFetch<AdzunaSettings>("/settings/adzuna"),
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
