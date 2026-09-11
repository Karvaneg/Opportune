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

/** Un événement de l'historique de validation d'une décision. */
export interface DecisionHistoryEvent {
  status: DecisionStatus;
  at: string; // ISO 8601
  comment: string | null;
}

/**
 * Détail d'une recommandation (`GET /recommendations/{id}`) — la décision persistée,
 * historique inclus. `title`/`company` sont résolus depuis l'offre d'origine (OPP-112) ;
 * `null` si l'offre a disparu, auquel cas le front retombe sur `offer_id`.
 */
export interface RecommendationDetail {
  recommendation_id: string;
  candidate_id: string;
  offer_id: string;
  action: OfferAction;
  score: number;
  title: string | null;
  company: string | null;
  justification: string;
  status: DecisionStatus;
  comment: string | null;
  history: DecisionHistoryEvent[];
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

/** Résumé d'un run pour le listing (`GET /runs`) — volumétrie sans le détail. */
export interface RunSummary {
  run_id: string;
  candidate_id: string;
  executed_at: string; // ISO 8601
  evaluation_count: number;
  error_count: number;
}

/** Réponse paginée de `GET /runs`. */
export interface RunsPage {
  items: RunSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/**
 * Réponse d'une confirmation d'action sortante (`POST /applications/{id}/confirm`, OPP-110).
 * Exécution **simulée** à ce stade (`status`). `already_confirmed` porte l'idempotence :
 * re-confirmer la même cible renvoie l'action existante sans la dupliquer.
 */
export interface ActionConfirmation {
  action_id: string;
  status: string;
  already_confirmed: boolean;
}

/** Offre persistée renvoyée par `POST /offers` (intake d'offre collée, OPP-145). */
export interface OfferSummary {
  id: string;
  title: string;
  company: string;
  location: string;
  skills: string[];
  seniority: string;
  contract_type: string;
  summary: string;
  source: string;
  url: string;
}

/** Identité du porteur du jeton (`GET /me`) — sonde d'authentification. */
export interface Me {
  id: string | null;
  role: string | null;
  owned_count: number;
  /** Candidats du périmètre du porteur — cible d'un lancement de run (OPP-143). */
  owned_candidate_ids: string[];
}

/** Corps d'erreur uniforme de l'API : `{ "error": "..." }`. */
export interface ApiErrorBody {
  error: string;
}
