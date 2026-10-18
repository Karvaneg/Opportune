import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import { apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";
import type { ActionConfirmation, RecommendationDetail } from "./types";

// Clé de cache du détail d'une recommandation. Distincte des `runKeys` : une reco se
// consulte par son id stable (cf. decision_id), indépendamment du run qui l'a produite.
export const recommendationKeys = {
  detail: (id: string) => ["recommendation", id] as const,
};

/** Verbes de validation humaine acceptés par `POST /recommendations/{id}/decision`. */
export type DecisionVerb = "approve" | "reject" | "defer";

export interface ValidateVariables {
  decision: DecisionVerb;
  comment?: string;
}

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

/**
 * Validation humaine d'une recommandation : `POST /recommendations/{id}/decision` (OPP-108).
 * Bâtie sur le socle des mutations (OPP-105) : jeton injecté, puis invalidation du détail
 * → `status` et historique se rafraîchissent en direct, sans rechargement. Les erreurs
 * (400/403/404) remontent telles quelles (`ApiHttpError`) pour affichage par l'appelant.
 */
export function useValidateRecommendation(recommendationId: string) {
  return useApiMutation<RecommendationDetail, ValidateVariables>({
    mutationFn: (variables, token) =>
      apiPost<RecommendationDetail>(
        `/recommendations/${encodeURIComponent(recommendationId)}/decision`,
        token,
        variables,
      ),
    invalidateKeys: () => [recommendationKeys.detail(recommendationId)],
  });
}

/**
 * Re-score ciblé d'une offre : `POST /candidates/{cid}/offers/{oid}/rescore` (OPP-150).
 * Recalcule le score de l'offre et rafraîchit sa décision. Réservé aux offres **non encore
 * arbitrées** (le back préserve de toute façon une décision humaine). Au succès, invalide le
 * détail de la reco (score à jour, affiché ici) et les listes de runs (où le `decision_status`
 * live est relu). Erreurs (404 si offre inconnue/non évaluable) remontées telles quelles.
 */
export function useRescoreOffer(
  recommendationId: string,
  candidateId: string,
  offerId: string,
) {
  return useApiMutation<RecommendationDetail, void>({
    mutationFn: (_variables, token) =>
      apiPost<RecommendationDetail>(
        `/candidates/${encodeURIComponent(candidateId)}/offers/${encodeURIComponent(offerId)}/rescore`,
        token,
        {},
      ),
    invalidateKeys: () => [recommendationKeys.detail(recommendationId), ["runs"], ["run"]],
  });
}

/**
 * Confirmation explicite d'une candidature : `POST /applications/{id}/confirm` (OPP-110).
 * Double consentement côté UI ; le body est `{confirm: true}` (booléen strict exigé par le
 * back). Idempotent (`already_confirmed`). Exige une décision humaine `approved` côté back,
 * sinon 409 — remonté tel quel (`ApiHttpError`) pour être expliqué à l'utilisateur.
 * Au succès, invalide le détail de la reco : l'intention notée (`application`) est relue et
 * son badge persistant (avec sa date) s'affiche sans rechargement.
 */
export function useConfirmApplication(recommendationId: string) {
  return useApiMutation<ActionConfirmation, void>({
    mutationFn: (_variables, token) =>
      apiPost<ActionConfirmation>(
        `/applications/${encodeURIComponent(recommendationId)}/confirm`,
        token,
        { confirm: true },
      ),
    invalidateKeys: () => [recommendationKeys.detail(recommendationId)],
  });
}
