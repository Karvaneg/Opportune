import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "./client";
import type { RunDetail, RunRecommendationsPage, RunsPage } from "./types";

// Clés de cache stables et hiérarchiques. `run(runId)` est le préfixe commun à `detail`
// et `recommendations` : l'invalider rafraîchit toutes les vues d'un run (cf. OPP-105).
export const runKeys = {
  list: (page: number) => ["runs", page] as const,
  run: (runId: string) => ["run", runId] as const,
  detail: (runId: string) => ["run", runId, "detail"] as const,
  recommendations: (runId: string, page: number) =>
    ["run", runId, "recommendations", page] as const,
};

/** Listing paginé des runs du périmètre : `GET /runs`. */
export function useRuns(page: number) {
  const { token } = useAuth();
  return useQuery({
    queryKey: runKeys.list(page),
    queryFn: () => apiFetch<RunsPage>(`/runs?page=${page}`, token!),
    enabled: Boolean(token),
    placeholderData: keepPreviousData, // évite le clignotement entre pages
  });
}

/** Détail d'un run : `GET /runs/{run_id}`. */
export function useRunDetail(runId: string) {
  const { token } = useAuth();
  return useQuery({
    queryKey: runKeys.detail(runId),
    queryFn: () => apiFetch<RunDetail>(`/runs/${encodeURIComponent(runId)}`, token!),
    enabled: Boolean(token) && runId.length > 0,
  });
}

/** Recommandations paginées d'un run : `GET /runs/{run_id}/recommendations`. */
export function useRunRecommendations(runId: string, page: number) {
  const { token } = useAuth();
  return useQuery({
    queryKey: runKeys.recommendations(runId, page),
    queryFn: () =>
      apiFetch<RunRecommendationsPage>(
        `/runs/${encodeURIComponent(runId)}/recommendations?page=${page}`,
        token!,
      ),
    enabled: Boolean(token) && runId.length > 0,
    placeholderData: keepPreviousData, // évite le clignotement entre pages
  });
}
