import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiDelete, apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";
import type {
  AdvisoryStatus,
  DecisionStatus,
  RecommendationItem,
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
  list: (page: number, candidateId = "") => ["runs", page, candidateId] as const,
  run: (runId: string) => ["run", runId] as const,
  detail: (runId: string) => ["run", runId, "detail"] as const,
  recommendations: (runId: string, page: number, advisory = "", decision = "") =>
    ["run", runId, "recommendations", page, advisory, decision] as const,
};

/** Réponse de `POST /candidates/{id}/recommendations` (lancement d'un run, non paginée). */
export interface LaunchRunResult {
  run_id: string;
  items: RecommendationItem[];
  total: number;
  errors: string[];
}

/**
 * Lance un run d'analyse pour un candidat : `POST /candidates/{id}/recommendations` (OPP-143).
 * La variable de mutation est le `candidate_id`. Au succès, invalide la liste des runs →
 * le nouveau run apparaît en tête sans rechargement. Erreurs remontées telles quelles.
 */
export function useLaunchRun() {
  return useApiMutation<LaunchRunResult, string>({
    mutationFn: (candidateId, token) =>
      apiPost<LaunchRunResult>(
        `/candidates/${encodeURIComponent(candidateId)}/recommendations`,
        token,
        {},
      ),
    invalidateKeys: () => [["runs"]],
  });
}

/**
 * Supprime un run : `DELETE /runs/{id}` (OPP-144). Variable = run_id. Au succès, invalide
 * la liste des runs → la ligne disparaît. Le back garde la propriété + le rôle reviewer.
 */
export function useDeleteRun() {
  return useApiMutation<{ deleted: string }, string>({
    mutationFn: (runId, token) =>
      apiDelete<{ deleted: string }>(`/runs/${encodeURIComponent(runId)}`, token),
    invalidateKeys: () => [["runs"]],
  });
}

/**
 * Listing paginé des runs du périmètre : `GET /runs`. `candidateId` (optionnel) restreint le
 * listing à un seul candidat (owner-gated côté API) — utilisé par le guide d'accueil pour savoir
 * si *ce* candidat a déjà un run, sans compter ceux des autres candidats du périmètre (OPP-177).
 */
export function useRuns(page: number, candidateId?: string) {
  const { token } = useAuth();
  const scoped = candidateId
    ? `&candidate_id=${encodeURIComponent(candidateId)}`
    : "";
  return useQuery({
    queryKey: runKeys.list(page, candidateId ?? ""),
    queryFn: () => apiFetch<RunsPage>(`/runs?page=${page}${scoped}`, token!),
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
