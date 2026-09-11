import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "./client";
import type { RecommendationDetail } from "./types";

// Clé de cache du détail d'une recommandation. Distincte des `runKeys` : une reco se
// consulte par son id stable (cf. decision_id), indépendamment du run qui l'a produite.
export const recommendationKeys = {
  detail: (id: string) => ["recommendation", id] as const,
};

/** Détail d'une recommandation : `GET /recommendations/{id}` (cf. OPP-107/112). */
export function useRecommendation(recommendationId: string) {
  const { token } = useAuth();
  return useQuery({
    queryKey: recommendationKeys.detail(recommendationId),
    queryFn: () =>
      apiFetch<RecommendationDetail>(
        `/recommendations/${encodeURIComponent(recommendationId)}`,
        token!,
      ),
    enabled: Boolean(token) && recommendationId.length > 0,
  });
}
