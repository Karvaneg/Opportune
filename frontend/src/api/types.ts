// Contrat de l'API Hermes (V2), fidèle à python/src/api/app.py — OPP-100.
// Le frontend ne déduit AUCUNE information métier absente de ce contrat.

/** Pré-évaluation automatique figée (PRE_EVALUATION_STATUSES côté API). */
export type AdvisoryStatus = "approved" | "pending" | "rejected";

/** État de validation humaine courant (VALIDATION_STATUSES côté API). */
export type DecisionStatus = "pending" | "approved" | "rejected" | "deferred";

/** Action auto figée. `""` = non renseignée au run-time (valeur par défaut côté API). */
export type OfferAction = "postuler" | "a_etudier" | "ignorer" | "indeterminee" | "";

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
  /** `null` pour une formation (OPP-166) : pas de score d'adéquation. */
  score: number | null;
  title: string | null;
  company: string | null;
  /** Type de l'offre d'origine (OPP-166), ou `null` si l'offre a disparu. */
  kind: OfferKind | null;
  /** Lien vers l'annonce d'origine (OPP-112), `null`/vide si absent ou offre disparue. */
  url: string | null;
  /** Date d'ingestion de l'offre dans Opportune (ISO 8601), `null` si l'offre a disparu. */
  created_at: string | null;
  justification: string;
  status: DecisionStatus;
  comment: string | null;
  history: DecisionHistoryEvent[];
  /**
   * Intention de candidater déjà notée (OPP-096), ou `null` si aucune. `confirmed_at` est
   * la date de la note ; `status` reste technique (`simulated` en V2, aucun envoi réel) et
   * n'est pas affiché tel quel — le front en fait un libellé lisible.
   */
  application: ApplicationIntent | null;
}

/**
 * État persistant de l'intention de candidater (lue dans le détail d'une recommandation),
 * avec son cycle de vie. `applied` = l'utilisateur a déclaré avoir **réellement candidaté**
 * (`applied_at` = quand), `false` tant qu'il n'a noté que l'intention. Aucun envoi réel.
 */
export interface ApplicationIntent {
  confirmed: boolean;
  confirmed_at: string; // ISO 8601
  status: string;
  applied: boolean;
  applied_at: string | null; // ISO 8601, ou null si pas encore candidaté
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

/**
 * Type d'offre (OPP-166) : `emploi` (poste à pourvoir, scoré) ou `formation` (cursus /
 * certification / POE, non scoré — son but est d'acquérir des compétences, pas d'en exiger).
 */
export type OfferKind = "emploi" | "formation";

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
  created_at: string; // ISO 8601, date d'ingestion (OPP-152)
  kind: OfferKind;
}

/** Bande de recommandation dérivée du score (seuils côté serveur) — `null` si non noté. */
export type RecommendationAction = "postuler" | "a_etudier" | "ignorer";

/**
 * Ligne du catalogue d'offres (`GET /offers`, OPP-146). `score` est le match pour le
 * `candidate_id` demandé — `null` si aucun candidat n'est ciblé ou si l'offre n'est pas
 * évaluable. `action` est la bande (`postuler`/`a_etudier`/`ignorer`) calculée par le
 * serveur depuis ce score : c'est elle qui pilote l'affichage, pour ne pas dupliquer les
 * seuils côté client. Plus léger que `OfferSummary` : pas de `skills`/`summary` (vue liste).
 */
export interface CatalogOffer {
  id: string;
  title: string;
  company: string;
  location: string;
  contract_type: string;
  seniority: string;
  source: string;
  url: string;
  created_at: string; // ISO 8601
  kind: OfferKind; // OPP-166 : une `formation` est badgée, pas scorée
  score: number | null;
  action: RecommendationAction | null;
  /**
   * Avancement **du candidat** sur cette offre (OPP-164), pour l'entonnoir du cockpit —
   * indépendant du score de l'algo. `decision_status` est `null` tant qu'aucune décision n'a
   * été prise (ou sans candidat ciblé) ; `applied` = candidature déclarée.
   */
  decision_status: DecisionStatus | null;
  applied: boolean;
}

/**
 * Agrégats de décision d'un candidat (`GET /candidates/{id}/stats`, OPP-163) — alimente les
 * cartes du cockpit. `a_etudier` / `a_postuler` : offres à l'action recommandée correspondante
 * et non encore tranchées (piles « à traiter ») ; `postule` : candidatures déclarées ;
 * `offres_total` : taille du pool évalué (formations comprises).
 */
export interface CandidateStats {
  a_etudier: number;
  a_postuler: number;
  postule: number;
  offres_total: number;
}

/**
 * Événement du flux d'activité du cockpit (`GET /candidates/{id}/activity`, OPP-165) :
 * décision tranchée, lettre, candidature déclarée ou offre ajoutée. `label` est prêt à
 * afficher (FR) ; `target_kind` indique vers quoi pointe le clic (`recommendation` → fiche,
 * `offer` → catalogue).
 */
export interface ActivityEvent {
  type: "letter" | "decision" | "application" | "offer";
  at: string; // ISO 8601
  label: string;
  target_kind: "recommendation" | "offer";
  target_id: string;
}

/** Réponse paginée de `GET /offers`. */
export interface OffersCatalogPage {
  items: CatalogOffer[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/**
 * Bilan d'une passe de collecte réelle (`POST /collect`, OPP-167). `stored` = offres neuves
 * persistées (« nouvelles »), `duplicates` = déjà connues, `failures` = analyses échouées
 * (cardinal, détail côté serveur). `source_error` est non nul si la source elle-même a
 * échoué (identifiants Adzuna manquants, quota, réseau) : la passe s'arrête, le reste est
 * compté, et l'erreur est affichée telle quelle plutôt qu'un statut HTTP d'échec.
 */
export interface CollectionReport {
  collected: number;
  stored: number;
  duplicates: number;
  failures: number;
  source_error: string | null;
  /** Offres neuves sans compétences qui ont déclenché une récupération de la page complète (OPP-169). */
  enriched: number;
  /** Parmi `enriched`, combien ont effectivement gagné des compétences après ré-analyse. */
  enriched_recovered: number;
}

/** Statut d'un job de collecte asynchrone (OPP-170). */
export type CollectionJobStatus = "running" | "done" | "failed";

/** Compteurs d'avancement d'une passe en cours (mêmes champs que le bilan, `failures` en cardinal). */
export interface CollectionProgress {
  collected: number;
  stored: number;
  duplicates: number;
  failures: number;
  enriched: number;
  enriched_recovered: number;
}

/**
 * État d'un job de collecte asynchrone (`GET /collect/{job_id}`, OPP-170). `report` est le
 * bilan complet une fois `status === "done"`, sinon `null` ; `error` porte le message en cas
 * de `failed`. `progress` suit l'avancement pendant que le job tourne (`running`).
 */
export interface CollectionJob {
  job_id: string;
  status: CollectionJobStatus;
  progress: CollectionProgress;
  report: CollectionReport | null;
  error: string | null;
}

/** Réponse du démarrage d'une collecte (`POST /collect` → 202, OPP-170). */
export interface CollectionJobStart {
  job_id: string;
}

/** Provenance d'une lettre : générée par le LLM (`ai`) ou éditée à la main (`human`). */
export type LetterSource = "ai" | "human";

/**
 * Lettre de motivation persistée (`GET/POST/PUT /recommendations/{id}/letter`, OPP-147).
 * `source` pilote l'affichage et l'avertissement de régénération : une lettre `human`
 * ne doit pas être écrasée sans confirmation explicite (`model` vide pour une édition).
 */
export interface Letter {
  recommendation_id: string;
  body: string;
  source: LetterSource;
  model: string;
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
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
