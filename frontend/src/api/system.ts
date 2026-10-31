import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "./client";
import { useApiMutation } from "./mutations";

// Mise en route du LLM local au 1er lancement (OPP-193). Le front sonde la disponibilité
// (Ollama joignable, modèle présent, RAM) et, si le modèle manque, lance son téléchargement
// puis en suit la progression. Contrat miroir de `api.app` (routes /system/llm/*).

export type MemoryLevel = "ok" | "tight" | "insufficient" | "unknown";

export interface LlmMemory {
  level: MemoryLevel;
  total_gb: number | null;
  recommended_gb: number;
  minimum_gb: number;
}

export type SetupState = "idle" | "running" | "done" | "failed";

export interface LlmSetup {
  state: SetupState;
  status: string;
  fraction: number;
  error: string | null;
}

export interface LlmStatus {
  ollama_reachable: boolean;
  model: string;
  model_present: boolean;
  memory: LlmMemory;
  setup: LlmSetup;
}

const SETUP_POLL_INTERVAL_MS = 1000;

export const systemKeys = {
  llmStatus: ["system", "llm", "status"] as const,
  llmSetup: ["system", "llm", "setup"] as const,
};

/** Disponibilité du LLM local (Ollama joignable, modèle présent, verdict RAM). */
export function useLlmStatus() {
  return useQuery({
    queryKey: systemKeys.llmStatus,
    queryFn: () => apiFetch<LlmStatus>("/system/llm/status"),
  });
}

/** Pourquoi le LLM n'est pas prêt : son modèle s'installe, ou le moteur Ollama est injoignable. */
export type LlmNotReadyReason = "preparing" | "unreachable";

/**
 * Le LLM local est-il utilisable *maintenant* ? Dérivé de {@link useLlmStatus} pour les actions
 * qui en dépendent (lancer une analyse, collecter avec enrichissement). Permet de les désactiver
 * individuellement plutôt que de bloquer toute l'app (OPP-195) : la consultation (espace Démo,
 * offres déjà en base) reste accessible sans LLM.
 *
 * Fail-open : statut en cours de chargement, en erreur ou indéterminable (vieux backend) → on
 * considère le LLM prêt. On préfère laisser tenter l'action — qui signalera elle-même un éventuel
 * échec — plutôt que de verrouiller à tort sur une incertitude.
 */
export function useLlmReady(): { ready: boolean; reason: LlmNotReadyReason | null } {
  const status = useLlmStatus();
  if (status.isLoading || status.isError || !status.data) return { ready: true, reason: null };
  if (status.data.model_present) return { ready: true, reason: null };
  return { ready: false, reason: status.data.ollama_reachable ? "preparing" : "unreachable" };
}

/**
 * Lance le téléchargement du modèle : `POST /system/llm/setup`. Idempotent côté serveur.
 *
 * Invalide la clé de sondage après succès. Au (re)lancement, en particulier un « Réessayer »
 * après échec, la donnée en cache est `failed`/`idle` : `refetchInterval` resterait à `false` et
 * le sondage ne repartirait pas. L'invalidation force un refetch, le serveur répond `running`,
 * et le sondage reprend.
 */
export function useStartLlmSetup() {
  return useApiMutation<LlmSetup, void>({
    mutationFn: () => apiPost<LlmSetup>("/system/llm/setup", {}),
    invalidateKeys: () => [systemKeys.llmSetup],
  });
}

/**
 * Sonde l'avancement du téléchargement : `GET /system/llm/setup`. Tant que l'état est
 * `running`, rafraîchi chaque seconde ; s'arrête sinon. Désactivée tant que `enabled` est faux
 * (aucun téléchargement en cours).
 */
export function useLlmSetupProgress(enabled: boolean) {
  return useQuery({
    queryKey: systemKeys.llmSetup,
    queryFn: () => apiFetch<LlmSetup>("/system/llm/setup"),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? SETUP_POLL_INTERVAL_MS : false,
  });
}
