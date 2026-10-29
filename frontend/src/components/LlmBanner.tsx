import { useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  systemKeys,
  useLlmSetupProgress,
  useLlmStatus,
  useStartLlmSetup,
  type LlmMemory,
} from "../api/system";

/**
 * Bandeau de mise en route du LLM local (OPP-193, repensé en OPP-195). Tant que le modèle n'est
 * pas présent, il invite à l'installer (barre de progression) ou signale qu'Ollama est
 * injoignable — **sans bloquer l'app**. La consultation (espace Démo, offres déjà en base) reste
 * accessible ; seules les actions qui exigent le LLM se désactivent d'elles-mêmes (cf.
 * `useLlmReady`). Une fois le modèle prêt, le bandeau disparaît.
 *
 * Fail-open : statut en cours de chargement, en erreur ou indéterminable (vieux backend sans la
 * route) → pas de bandeau ; les fonctions qui exigent le LLM signaleront elles-mêmes l'absence.
 */
export function LlmBanner() {
  const status = useLlmStatus();

  if (status.isLoading || status.isError || !status.data || status.data.model_present) {
    return null;
  }

  return <LlmSetup status={status.data} onReady={status.refetch} />;
}

function LlmSetup({
  status,
  onReady,
}: {
  status: NonNullable<ReturnType<typeof useLlmStatus>["data"]>;
  onReady: () => void;
}) {
  const queryClient = useQueryClient();
  const start = useStartLlmSetup();
  // Un téléchargement déjà en cours au (re)montage (ex. changement de page) : on reprend le sondage.
  const [downloading, setDownloading] = useState(status.setup.state === "running");
  const progress = useLlmSetupProgress(downloading);
  const setup = progress.data ?? status.setup;

  // Dès que le modèle est prêt, on réinterroge le statut : `model_present` passe à vrai et le
  // bandeau disparaît.
  useEffect(() => {
    if (setup.state === "done") {
      queryClient.invalidateQueries({ queryKey: systemKeys.llmStatus });
      onReady();
    }
  }, [setup.state, queryClient, onReady]);

  if (!status.ollama_reachable) {
    return (
      <Banner tone="danger">
        <span className="min-w-0 text-danger">
          Assistant local injoignable : le moteur Ollama n'a pas répondu. Les analyses et la
          rédaction de lettres resteront indisponibles tant qu'il n'est pas démarré.
        </span>
        <button type="button" onClick={() => onReady()} className={bannerButton}>
          Réessayer
        </button>
      </Banner>
    );
  }

  const percent = Math.round(setup.fraction * 100);
  const failed = setup.state === "failed";

  return (
    <Banner tone="brand">
      <div className="flex min-w-0 flex-col gap-1">
        <span className="text-brand">
          {downloading && !failed
            ? `Préparation de l'assistant local… ${percent}%`
            : failed
              ? `Le téléchargement du modèle a échoué${setup.error ? ` : ${setup.error}` : ""}.`
              : `Opportune utilise un modèle d'IA local (${status.model}, ~3 Go) à installer une seule fois. Tu peux explorer l'espace Démo en attendant.`}
        </span>
        {downloading && !failed && (
          <div className="h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-ink/10">
            <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${percent}%` }} />
          </div>
        )}
        <MemoryNotice memory={status.memory} />
      </div>
      {(!downloading || failed) && (
        <button
          type="button"
          onClick={() => {
            setDownloading(true);
            start.mutate();
          }}
          disabled={start.isPending}
          className={bannerButton}
        >
          {failed ? "Réessayer le téléchargement" : "Installer le modèle"}
        </button>
      )}
    </Banner>
  );
}

/** Avertissement RAM honnête selon le verdict du backend (OPP-193). `ok` → rien à dire. */
function MemoryNotice({ memory }: { memory: LlmMemory }) {
  if (memory.level === "ok") return null;

  const text =
    memory.level === "insufficient"
      ? `Ta machine dispose de ${memory.total_gb} Go de RAM, sous le minimum conseillé de ${memory.minimum_gb} Go. Opportune risque d'être très lent, voire instable.`
      : memory.level === "tight"
        ? `Ta machine dispose de ${memory.total_gb} Go de RAM (recommandé : ${memory.recommended_gb} Go). Ça fonctionnera, mais les traitements IA pourront être lents.`
        : "Impossible de mesurer la RAM disponible. Si la machine est modeste, les traitements IA pourront être lents.";

  const tone = memory.level === "insufficient" ? "text-danger" : "text-warning-text";

  return <span className={`text-xs ${tone}`}>{text}</span>;
}

const bannerButton =
  "shrink-0 rounded-md px-3 py-1.5 text-sm font-medium text-brand transition-colors hover:bg-brand/15 disabled:opacity-50";

function Banner({ tone, children }: { tone: "brand" | "danger"; children: ReactNode }) {
  const border = tone === "danger" ? "border-danger/30 bg-danger/10" : "border-brand/30 bg-brand/10";
  return (
    <div className={`border-b ${border}`}>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm sm:px-6">
        {children}
      </div>
    </div>
  );
}
