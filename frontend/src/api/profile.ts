import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, apiPut } from "./client";
import { useApiMutation } from "./mutations";
import { offerKeys } from "./offers";
import type { CandidateProfile } from "./types";

// Clé de cache du profil : par candidat. Le PUT invalide cette clé (relecture) et le catalogue
// (les scores de match peuvent changer quand les compétences du profil évoluent).
export const profileKeys = {
  all: ["profile"] as const,
  candidate: (candidateId: string) => ["profile", candidateId] as const,
};

/**
 * Profil d'un candidat : `GET /candidates/{id}/profile` (OPP-158). Alimente le panneau de
 * consultation/édition des compétences du cockpit. Désactivée sans candidat ciblé. Un `404`
 * (candidat sans profil) remonte comme erreur — l'appelant l'affiche sobrement.
 */
export function useProfile(candidateId: string) {
  const { token } = useAuth();
  return useQuery({
    queryKey: profileKeys.candidate(candidateId),
    queryFn: () =>
      apiFetch<CandidateProfile>(
        `/candidates/${encodeURIComponent(candidateId)}/profile`,
        token!,
      ),
    enabled: Boolean(token) && candidateId !== "",
  });
}

export interface UpdateProfileSkillsVariables {
  candidateId: string;
  /** Liste **complète** des compétences après édition (remplacement, pas delta). */
  skills: string[];
}

/**
 * Met à jour les compétences du profil : `PUT /candidates/{id}/profile` (OPP-158). Reviewer
 * uniquement (curation, comme l'ajout d'offre). Le back normalise + revalide (liste vide → 400).
 * Au succès, invalide le profil **et** le catalogue (préfixe `["offers"]`) : combler les
 * compétences manquantes change les scores de match, qui doivent se rafraîchir sans rechargement.
 */
export function useUpdateProfileSkills() {
  return useApiMutation<CandidateProfile, UpdateProfileSkillsVariables>({
    mutationFn: ({ candidateId, skills }, token) =>
      apiPut<CandidateProfile>(
        `/candidates/${encodeURIComponent(candidateId)}/profile`,
        token,
        { skills },
      ),
    invalidateKeys: ({ candidateId }) => [profileKeys.candidate(candidateId), offerKeys.all],
  });
}
