import type { DecisionStatus } from "./types";

/**
 * Étapes de l'entonnoir de candidature du cockpit (OPP-164), piloté par **mes décisions** et
 * non par le score de l'algo. Miroir de `app/candidate_stats.funnel_stage` côté back — garder
 * les deux alignés. `null` = hors entonnoir (offre rejetée / reportée).
 */
export type FunnelStage = "a_etudier" | "a_postuler" | "postule";

export const FUNNEL_LABELS: Record<FunnelStage, string> = {
  a_etudier: "À étudier",
  a_postuler: "À postuler",
  postule: "Postulé",
};

/**
 * Classe une offre dans l'entonnoir d'après la décision humaine et l'état de candidature.
 * La candidature prime (candidatée → « postulé » même si la décision a changé) ; une offre
 * non décidée (`null`) est « à étudier » ; rejetée / reportée → `null` (hors entonnoir).
 */
export function funnelStage(
  decisionStatus: DecisionStatus | null,
  applied: boolean,
): FunnelStage | null {
  if (applied) return "postule";
  if (decisionStatus === "approved") return "a_postuler";
  if (decisionStatus === null || decisionStatus === "pending") return "a_etudier";
  return null; // rejected / deferred
}

/** Vrai si `value` est une étape d'entonnoir connue (validation d'un param d'URL). */
export function isFunnelStage(value: string | null): value is FunnelStage {
  return value === "a_etudier" || value === "a_postuler" || value === "postule";
}
