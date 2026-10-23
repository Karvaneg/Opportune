import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { ActivityEvent } from "./types";

// Clé de cache du flux d'activité : par candidat (refetch au remontage du cockpit).
export const activityKeys = {
  all: ["activity"] as const,
  candidate: (candidateId: string) => ["activity", candidateId] as const,
};

/**
 * Flux d'activité récente d'un candidat : `GET /candidates/{id}/activity` (OPP-165). Alimente
 * le bloc « Dernière activité » du cockpit. Désactivé sans candidat ciblé (périmètre vide).
 */
export function useCandidateActivity(candidateId: string) {
  return useQuery({
    queryKey: activityKeys.candidate(candidateId),
    queryFn: () =>
      apiFetch<{ items: ActivityEvent[] }>(
        `/candidates/${encodeURIComponent(candidateId)}/activity`,
      ),
    enabled: candidateId !== "",
  });
}
