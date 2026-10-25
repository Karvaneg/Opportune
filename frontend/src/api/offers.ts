import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";
import type {
  CollectionJob,
  CollectionJobStart,
  OffersCatalogPage,
  OfferSummary,
  RecommendationDetail,
} from "./types";

// Clé de cache du catalogue : page + candidat ciblé + étape d'entonnoir (chaque combinaison a
// son cache). `all` est le préfixe commun (invalidation de toutes les variantes, cf. `useAddOffer`).
export const offerKeys = {
  all: ["offers"] as const,
  catalog: (page: number, candidateId: string, stage: string) =>
    ["offers", page, candidateId, stage] as const,
};

/**
 * Catalogue paginé des offres : `GET /offers` (OPP-146). `candidateId` (optionnel) annote
 * chaque offre de son score de match pour ce candidat ; vide = catalogue brut (scores
 * `null`). `stage` (optionnel, OPP-164) filtre **côté serveur** par étape d'entonnoir, sur
 * tout le pool avant pagination — le `total` et les cartes du cockpit concordent alors même
 * au-delà d'une page. Plus récentes d'abord (tri serveur, OPP-152).
 */
export function useOffers(page: number, candidateId: string, stage = "") {
  const params = new URLSearchParams({ page: String(page) });
  if (candidateId) params.set("candidate_id", candidateId);
  if (stage) params.set("stage", stage);
  return useQuery({
    queryKey: offerKeys.catalog(page, candidateId, stage),
    queryFn: () => apiFetch<OffersCatalogPage>(`/offers?${params}`),
    placeholderData: keepPreviousData, // évite le clignotement entre pages/candidats/étapes
  });
}

export interface AddOfferVariables {
  /** Texte brut de l'offre. Fournir `text` OU `url` (le texte prime si les deux sont là). */
  text?: string;
  /** URL de l'offre : le back récupère la page et en extrait le texte (OPP-148). */
  url?: string;
  /** Provenance (défaut « collée » pour le texte, le domaine pour une URL). */
  source?: string;
}

/**
 * Ajoute une offre, par texte collé (OPP-145) ou par URL (OPP-148) : `POST /offers`. Le back
 * analyse via LLM puis persiste (id dérivé du texte → pas de doublon). Latence LLM (+ fetch
 * pour une URL) → l'appelant gère l'attente. Erreurs remontées telles quelles : 400 (saisie
 * ou URL refusée/SSRF), 502 (analyse/LLM, ou récupération de l'URL impossible). Au succès,
 * invalide le catalogue (préfixe `["offers"]`, toutes pages/candidats) pour que la nouvelle
 * offre y apparaisse sans rechargement (OPP-161).
 */
export function useAddOffer() {
  return useApiMutation<OfferSummary, AddOfferVariables>({
    mutationFn: (variables) => apiPost<OfferSummary>("/offers", variables),
    invalidateKeys: () => [offerKeys.all],
  });
}

export interface CollectOffersVariables {
  /** Mots-clés de recherche (Adzuna `what`) — optionnel. */
  what?: string;
  /** Localisation (Adzuna `where`), ex. « Paris » — optionnel. */
  where?: string;
}

// Cadence de sondage d'un job de collecte en cours (ms). Une passe dure des minutes
// (~40 s/offre neuve) : un sondage à la seconde et demie suffit à suivre l'avancement sans
// marteler le serveur.
const COLLECT_POLL_INTERVAL_MS = 1500;

export const collectJobKeys = {
  job: (jobId: string) => ["collect-job", jobId] as const,
};

// Suivi **global** de la collecte (OPP-208) : clé unique (pas de job_id), pour un indicateur
// persistant qui survit au changement de page.
export const activeCollectKey = ["collect-active"] as const;

/**
 * Démarre une passe de collecte réelle (Adzuna) : `POST /collect` → `202 { job_id }` (OPP-170).
 * Reviewer uniquement (curation du pool partagé, comme `useAddOffer`). La collecte est
 * **asynchrone** : cette mutation rend la main aussitôt avec un `job_id` ; l'avancement et le
 * bilan se suivent ensuite via `useCollectJob`. Un `409` (via `ApiHttpError`) signale qu'une
 * collecte est déjà en cours — un seul job à la fois côté serveur.
 */
export function useStartCollect() {
  return useApiMutation<CollectionJobStart, CollectOffersVariables>({
    mutationFn: (variables) =>
      apiPost<CollectionJobStart>("/collect", variables),
  });
}

/**
 * Sonde l'état d'un job de collecte : `GET /collect/{job_id}` (OPP-170). Tant que le job est
 * `running`, la requête se rafraîchit à `COLLECT_POLL_INTERVAL_MS` ; dès qu'il est `done` ou
 * `failed`, le sondage s'arrête (`refetchInterval` → `false`). Désactivée tant qu'aucun job
 * n'est lancé (`jobId` nul). L'invalidation du catalogue à la complétion est laissée à
 * l'appelant (il connaît le `stored` final et évite de recharger pour rien).
 */
export function useCollectJob(jobId: string | null) {
  return useQuery({
    queryKey: collectJobKeys.job(jobId ?? ""),
    queryFn: () => apiFetch<CollectionJob>(`/collect/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? COLLECT_POLL_INTERVAL_MS : false,
  });
}

/**
 * Suit la collecte **active** sans connaître son `job_id` : `GET /collect` → `{ job | null }`
 * (OPP-208). Source d'un indicateur **global persistant** — contrairement à `useCollectJob`
 * (lié à un `job_id` local, perdu en changeant de page), il retrouve une passe en cours au
 * (re)montage de n'importe quel écran. Sonde tant qu'un job `running` existe, s'arrête sinon
 * (un job terminé n'est plus « actif » : son bilan reste du ressort de la page Offres).
 */
export function useActiveCollectJob() {
  return useQuery({
    queryKey: activeCollectKey,
    queryFn: () => apiFetch<{ job: CollectionJob | null }>("/collect"),
    refetchInterval: (query) =>
      query.state.data?.job?.status === "running" ? COLLECT_POLL_INTERVAL_MS : false,
  });
}

export interface EvaluateOfferVariables {
  candidateId: string;
  offerId: string;
}

/**
 * Ouvre la fiche d'une offre pour un candidat depuis le catalogue (OPP-160) : `POST
 * /candidates/{cid}/offers/{oid}/rescore`. Get-or-create — garantit qu'une décision existe
 * (score + décision `pending` créés si l'offre n'avait jamais été évaluée), **sans créer de
 * run**, et préserve une décision humaine déjà prise. Retourne le détail de la recommandation
 * (dont `recommendation_id`) vers lequel l'appelant navigue.
 *
 * Même route que `useRescoreOffer` (OPP-150, recommendations.ts) : garder les deux synchronisés
 * si le contrat bouge. La divergence est volontaire — ici pas de reco préexistante à invalider,
 * donc pas d'`invalidateKeys` (le catalogue se refetch au remontage de la page).
 */
export function useEvaluateOffer() {
  return useApiMutation<RecommendationDetail, EvaluateOfferVariables>({
    mutationFn: ({ candidateId, offerId }) =>
      apiPost<RecommendationDetail>(
        `/candidates/${encodeURIComponent(candidateId)}/offers/${encodeURIComponent(offerId)}/rescore`,
        {},
      ),
  });
}
