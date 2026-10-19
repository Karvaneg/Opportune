import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch } from "./client";
import type { CandidateStats } from "./types";

// Clé de cache des agrégats : par candidat. Invalidée naturellement au changement de candidat ;
// un refetch au remontage du cockpit suffit à refléter décisions/candidatures récentes (MVP).
export const statsKeys = {
  all: ["stats"] as const,
  candidate: (candidateId: string) => ["stats", candidateId] as const,
};

/**
 * Agrégats de décision d'un candidat : `GET /candidates/{id}/stats` (OPP-163). Alimente les
 * trois cartes du cockpit (à étudier / à postuler / postulé) + le total du pool. Requête
 * désactivée sans candidat ciblé (périmètre vide) — le cockpit affiche alors un état neutre.
 */
export function useCandidateStats(candidateId: string) {
  const { token } = useAuth();
  return useQuery({
    queryKey: statsKeys.candidate(candidateId),
    queryFn: () =>
      apiFetch<CandidateStats>(
        `/candidates/${encodeURIComponent(candidateId)}/stats`,
        token!,
      ),
    enabled: Boolean(token) && candidateId !== "",
  });
}
