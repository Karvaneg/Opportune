import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "./client";
import type {
  AdvisoryStatus,
  DecisionStatus,
  RunDetail,
  RunRecommendationsPage,
  RunsPage,
} from "./types";

/** Filtres de statut de la liste des recommandations (OPP-109). `""` = pas de filtre. */
export interface RecommendationFilters {
  advisoryStatus?: AdvisoryStatus | "";
  decisionStatus?: DecisionStatus | "";
}

// Clés de cache stables et hiérarchiques. `run(runId)` est le préfixe commun à `detail`
// et `recommendations` : l'invalider rafraîchit toutes les vues d'un run (cf. OPP-105).
// Les filtres entrent dans la clé → chaque combinaison a son propre cache (OPP-109).
export const runKeys = {
  list: (page: number) => ["runs", page] as const,
  run: (runId: string) => ["run", runId] as const,
  detail: (runId: string) => ["run", runId, "detail"] as const,
  recommendations: (runId: string, page: number, advisory = "", decision = "") =>
    ["run", runId, "recommendations", page, advisory, decision] as const,
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

/**
 * Recommandations paginées d'un run : `GET /runs/{run_id}/recommendations`, filtrables par
 * statut (OPP-109). Les filtres vides ne sont pas envoyés (= « tous ») ; le back recalcule
 * `total`/`total_pages` après filtre. Seules des valeurs du contrat transitent (selects fermés).
 */
export function useRunRecommendations(
  runId: string,
  page: number,
  filters: RecommendationFilters = {},
) {
  const { token } = useAuth();
  const advisory = filters.advisoryStatus ?? "";
  const decision = filters.decisionStatus ?? "";

  const params = new URLSearchParams({ page: String(page) });
  if (advisory) params.set("advisory_status", advisory);
  if (decision) params.set("decision_status", decision);

  return useQuery({
    queryKey: runKeys.recommendations(runId, page, advisory, decision),
    queryFn: () =>
      apiFetch<RunRecommendationsPage>(
        `/runs/${encodeURIComponent(runId)}/recommendations?${params}`,
        token!,
      ),
    enabled: Boolean(token) && runId.length > 0,
    placeholderData: keepPreviousData, // évite le clignotement entre pages/filtres
  });
}
