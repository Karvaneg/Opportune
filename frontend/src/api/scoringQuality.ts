import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ScoringQuality } from "./types";

// Clé de cache : par candidat (refetch au remontage du cockpit, comme les compteurs). Préfixe
// `all` invalidé par les écritures qui changent une décision ou une candidature.
export const scoringQualityKeys = {
  all: ["scoring-quality"] as const,
  candidate: (candidateId: string) => ["scoring-quality", candidateId] as const,
};

/**
 * Scores des offres retenues contre rejetées : `GET /candidates/{id}/scoring-quality` (OPP-234).
 * Alimente la carte « Qualité du score » du cockpit. Désactivé sans candidat ciblé.
 */
export function useScoringQuality(candidateId: string) {
  return useQuery({
    queryKey: scoringQualityKeys.candidate(candidateId),
    queryFn: () =>
      apiFetch<ScoringQuality>(
        `/candidates/${encodeURIComponent(candidateId)}/scoring-quality`,
      ),
    enabled: candidateId !== "",
  });
}
