import { useQuery } from "@tanstack/react-query";
import { apiDelete, apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";
import { activityKeys } from "./activity";
import { offerKeys } from "./offers";
import { statsKeys } from "./stats";
import { scoringQualityKeys } from "./scoringQuality";
import type {
  ActionConfirmation,
  ApplicationIntent,
  RecommendationDetail,
  TrackingEvent,
  TrackingEventKind,
} from "./types";

// Clé de cache du détail d'une recommandation. Distincte des `runKeys` : une reco se
// consulte par son id stable (cf. decision_id), indépendamment du run qui l'a produite.
export const recommendationKeys = {
  detail: (id: string) => ["recommendation", id] as const,
};

/**
 * Vues qui dépendent de l'état d'une offre pour la recherche (décision, candidature, suivi) :
 * compteurs et activité de l'Accueil, qualité du score, listes d'offres filtrées par étape, et
 * listes de runs qui affichent et filtrent le statut de décision. Toute mutation qui change cet
 * état les invalide **toutes**, avec le détail de la recommandation : une liste unique évite
 * qu'une vue soit oubliée et réaffichée périmée au retour (OPP-244, `staleTime` de 30 s).
 */
function offerStateKeys(recommendationId: string) {
  return [
    recommendationKeys.detail(recommendationId),
    statsKeys.all,
    activityKeys.all,
    scoringQualityKeys.all,
    offerKeys.all,
    ["run"],
    ["runs"],
  ];
}

/** Verbes de validation humaine acceptés par `POST /recommendations/{id}/decision`. */
export type DecisionVerb = "approve" | "reject" | "defer";

export interface ValidateVariables {
  decision: DecisionVerb;
  comment?: string;
}

/** Détail d'une recommandation : `GET /recommendations/{id}` (cf. OPP-107/112). */
export function useRecommendation(recommendationId: string) {
  return useQuery({
    queryKey: recommendationKeys.detail(recommendationId),
    queryFn: () =>
      apiFetch<RecommendationDetail>(
        `/recommendations/${encodeURIComponent(recommendationId)}`,
      ),
    enabled: recommendationId.length > 0,
  });
}

/**
 * Validation humaine d'une recommandation : `POST /recommendations/{id}/decision` (OPP-108).
 * Bâtie sur le socle des mutations (OPP-105) : jeton injecté, puis invalidation du détail
 * → `status` et historique se rafraîchissent en direct, sans rechargement. La décision change
 * l'étape de l'offre : toutes les vues qui en dépendent sont invalidées (`offerStateKeys`). Les
 * erreurs (400/403/404) remontent telles quelles (`ApiHttpError`) pour affichage par l'appelant.
 */
export function useValidateRecommendation(recommendationId: string) {
  return useApiMutation<RecommendationDetail, ValidateVariables>({
    mutationFn: (variables) =>
      apiPost<RecommendationDetail>(
        `/recommendations/${encodeURIComponent(recommendationId)}/decision`,
        variables,
      ),
    invalidateKeys: () => offerStateKeys(recommendationId),
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
    mutationFn: (_variables) =>
      apiPost<RecommendationDetail>(
        `/candidates/${encodeURIComponent(candidateId)}/offers/${encodeURIComponent(offerId)}/rescore`,
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
    mutationFn: (_variables) =>
      apiPost<ActionConfirmation>(
        `/applications/${encodeURIComponent(recommendationId)}/confirm`,
        { confirm: true },
      ),
    invalidateKeys: () => [recommendationKeys.detail(recommendationId)],
  });
}

/**
 * Déclaration « j'ai candidaté » : `POST /applications/{id}/applied`. Pointage de suivi, pas
 * un envoi — aucune modale ni `{confirm}`. `applied_at` (optionnel) date une candidature
 * passée ; absent = aujourd'hui côté back. Exige une intention préalablement notée (sinon 409,
 * remonté tel quel). Au succès, invalide le détail : le badge « candidaté » (avec sa date)
 * s'affiche sans rechargement.
 */
export function useMarkApplied(recommendationId: string) {
  return useApiMutation<ApplicationIntent, { applied_at?: string }>({
    mutationFn: (variables) =>
      apiPost<ApplicationIntent>(
        `/applications/${encodeURIComponent(recommendationId)}/applied`,
        variables,
      ),
    invalidateKeys: () => offerStateKeys(recommendationId),
  });
}

/**
 * Annulation « finalement non, je n'ai pas candidaté » : `DELETE /applications/{id}/applied`.
 * Retire la date de candidature en conservant l'intention notée. Idempotent. Au succès,
 * invalide le détail pour rebasculer l'UI sur l'état « intention notée ».
 */
export function useUnmarkApplied(recommendationId: string) {
  return useApiMutation<ApplicationIntent, void>({
    mutationFn: (_variables) =>
      apiDelete<ApplicationIntent>(
        `/applications/${encodeURIComponent(recommendationId)}/applied`,
      ),
    invalidateKeys: () => offerStateKeys(recommendationId),
  });
}

/** Variables d'ajout d'un événement de suivi : type requis, date et commentaire optionnels. */
export interface AddTrackingVariables {
  kind: TrackingEventKind;
  event_date?: string; // ISO 8601 (date de l'entretien, éventuellement future)
  comment?: string;
}

/**
 * Ajout d'un événement de suivi post-candidature : `POST /applications/{id}/tracking` (OPP-223).
 * Pointage déclaratif, pas un envoi. Exige une candidature déclarée côté back (sinon 409, remonté
 * tel quel). Au succès, invalide le détail : la frise et la section de suivi se rafraîchissent
 * sans rechargement. Le back renvoie l'historique à jour (`{events}`).
 */
export function useAddTrackingEvent(recommendationId: string) {
  return useApiMutation<{ events: TrackingEvent[] }, AddTrackingVariables>({
    mutationFn: (variables) =>
      apiPost<{ events: TrackingEvent[] }>(
        `/applications/${encodeURIComponent(recommendationId)}/tracking`,
        variables,
      ),
    invalidateKeys: () => offerStateKeys(recommendationId),
  });
}
