import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPut } from "./client";
import { useApiMutation } from "./mutations";
import { offerKeys } from "./offers";
import { statsKeys } from "./stats";

/**
 * Une relance d'une candidature (OPP-235) : celle à faire aujourd'hui ou la prochaine prévue,
 * telle que le détail d'une recommandation la rend (`application.follow_up`).
 */
export interface FollowUpStep {
  /** Point de départ des relances : la candidature, ou le dernier entretien passé. */
  since: "candidature" | "entretien";
  start_date: string; // AAAA-MM-JJ
  due_date: string; // AAAA-MM-JJ
  /** Numéro de la relance (1 = première) sur `total` prévues. */
  step: number;
  total: number;
}

/** Relances d'une candidature : celle à faire aujourd'hui, et la prochaine pas encore due. */
export interface FollowUpState {
  due: FollowUpStep | null;
  next: FollowUpStep | null;
}

/** Délais de relance, en jours depuis le point de départ (`GET|PUT /settings/follow-up`). */
export interface FollowUpSettings {
  after_application: number[];
  after_interview: number[];
}

export const followUpKeys = {
  settings: ["settings", "follow-up"] as const,
};

/** Délais de relance enregistrés. */
export function useFollowUpSettings() {
  return useQuery({
    queryKey: followUpKeys.settings,
    queryFn: () => apiFetch<FollowUpSettings>("/settings/follow-up"),
  });
}

/** Enregistre les délais ; la carte « À relancer », le catalogue filtré et les fiches sont recalculés. */
export function useSaveFollowUpSettings() {
  return useApiMutation<FollowUpSettings, FollowUpSettings>({
    mutationFn: (variables) => apiPut<FollowUpSettings>("/settings/follow-up", variables),
    invalidateKeys: () => [followUpKeys.settings, statsKeys.all, offerKeys.all, ["recommendation"]],
  });
}

/** « 2e relance sur 3 ». */
export function followUpRank(item: FollowUpStep): string {
  const rank = item.step === 1 ? "1re" : `${item.step}e`;
  return `${rank} relance sur ${item.total}`;
}

/** « après l'entretien du 12/11/2026 ». */
export function followUpOrigin(item: FollowUpStep): string {
  const from = item.since === "entretien" ? "après l'entretien du" : "après la candidature du";
  return `${from} ${formatIsoDay(item.start_date)}`;
}

/** Date AAAA-MM-JJ en JJ/MM/AAAA ; valeur brute si illisible. */
export function formatIsoDay(isoDay: string): string {
  const [year, month, day] = isoDay.split("-");
  return year && month && day ? `${day}/${month}/${year}` : isoDay;
}
