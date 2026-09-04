import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "./client";
import type { RunDetail, RunRecommendationsPage } from "./types";

// Clés de cache stables et hiérarchiques (invalidation ciblée par run plus tard).
export const runKeys = {
  detail: (runId: string) => ["run", runId, "detail"] as const,
  recommendations: (runId: string, page: number) =>
    ["run", runId, "recommendations", page] as const,
};

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
