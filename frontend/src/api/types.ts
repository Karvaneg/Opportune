// Contrat de l'API Hermes (V2), fidèle à python/src/api/app.py — OPP-100.
// Le frontend ne déduit AUCUNE information métier absente de ce contrat.

/** Pré-évaluation automatique figée (PRE_EVALUATION_STATUSES côté API). */
export type AdvisoryStatus = "approved" | "pending" | "rejected";

/** État de validation humaine courant (VALIDATION_STATUSES côté API). */
export type DecisionStatus = "pending" | "approved" | "rejected" | "deferred";

/** Action auto figée. `""` = non renseignée au run-time (valeur par défaut côté API). */
export type OfferAction = "postuler" | "a_etudier" | "ignorer" | "";

/**
 * Évaluation telle que sérialisée dans le DÉTAIL d'un run (`GET /runs/{run_id}`).
 * ⚠ Ne porte PAS de `recommendation_id` : agir sur une reco passe par les items paginés.
 */
export interface RunEvaluation {
  offer_id: string;
  score: number; // entier
  decision_status: DecisionStatus;
  advisory_status: AdvisoryStatus;
  action: OfferAction;
  title: string;
  company: string;
  justification: string;
}

/** Réponse de `GET /runs/{run_id}`. */
export interface RunDetail {
  run_id: string;
  candidate_id: string;
  executed_at: string; // ISO 8601
  evaluations: RunEvaluation[];
  errors: string[];
}

/**
 * Item de la consultation paginée (`GET /runs/{run_id}/recommendations`).
 * Contrairement à `RunEvaluation`, il PORTE un `recommendation_id` (cible des actions futures).
 */
export interface RecommendationItem {
  recommendation_id: string;
  offer_id: string;
  score: number;
  advisory_status: AdvisoryStatus;
  action: OfferAction;
  decision_status: DecisionStatus;
  title: string;
  company: string;
  justification: string;
}

/** Réponse paginée de `GET /runs/{run_id}/recommendations`. */
export interface RunRecommendationsPage {
  run_id: string;
  items: RecommendationItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** Identité du porteur du jeton (`GET /me`) — sonde d'authentification. */
export interface Me {
  id: string | null;
  role: string | null;
  owned_count: number;
}

/** Corps d'erreur uniforme de l'API : `{ "error": "..." }`. */
export interface ApiErrorBody {
  error: string;
}
