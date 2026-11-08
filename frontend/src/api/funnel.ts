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

/**
 * Filtres du catalogue d'offres pilotés par l'URL (`?stage=`). Les trois étapes d'entonnoir,
 * plus `entretien` — un filtre **transverse** (OPP-223) : les offres candidatées dont un
 * entretien est à venir, et `a_relancer` (OPP-235), les candidatures dont une relance est due.
 * Ce n'est pas une étape d'entonnoir (une telle offre reste « postulé »),
 * d'où un type distinct de `FunnelStage`.
 */
export type CatalogStage = FunnelStage | "entretien" | "a_relancer";

export const CATALOG_STAGE_LABELS: Record<CatalogStage, string> = {
  ...FUNNEL_LABELS,
  entretien: "Entretien à venir",
  a_relancer: "À relancer",
};

/** Vrai si `value` est un filtre de catalogue connu (étape d'entonnoir, « entretien » ou « à relancer »). */
export function isCatalogStage(value: string | null): value is CatalogStage {
  return isFunnelStage(value) || value === "entretien" || value === "a_relancer";
}
