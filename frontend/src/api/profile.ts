import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPut } from "./client";
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
  return useQuery({
    queryKey: profileKeys.candidate(candidateId),
    queryFn: () =>
      apiFetch<CandidateProfile>(
        `/candidates/${encodeURIComponent(candidateId)}/profile`,
      ),
    enabled: candidateId !== "",
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
    mutationFn: ({ candidateId, skills }) =>
      apiPut<CandidateProfile>(
        `/candidates/${encodeURIComponent(candidateId)}/profile`,
        { skills },
      ),
    invalidateKeys: ({ candidateId }) => [profileKeys.candidate(candidateId), offerKeys.all],
  });
}

export interface UploadCvVariables {
  candidateId: string;
  /** CV PDF encodé base64 (le transport API est JSON-only — pas de multipart). */
  pdfBase64: string;
  /** Type de contrat du profil (un CV ne le porte pas) — repris du profil existant. */
  contractType: string;
}

/**
 * Importe un CV PDF pour (re)constituer le profil : `POST /candidates/{id}/profile/cv` (OPP-174).
 * Reviewer uniquement (curation du profil). Le back décode le base64, extrait le texte (pypdf) et
 * relance l'analyse LLM ; les faits corrigés à la main (verrouillés, OPP-138) sont préservés. Au
 * succès, invalide le profil **et** le catalogue : le nouveau profil change les scores de match.
 */
export function useUploadCv() {
  return useApiMutation<CandidateProfile, UploadCvVariables>({
    mutationFn: ({ candidateId, pdfBase64, contractType }) =>
      apiPost<CandidateProfile>(
        `/candidates/${encodeURIComponent(candidateId)}/profile/cv`,
        { pdf_base64: pdfBase64, contract_type: contractType },
      ),
    invalidateKeys: ({ candidateId }) => [profileKeys.candidate(candidateId), offerKeys.all],
  });
}
