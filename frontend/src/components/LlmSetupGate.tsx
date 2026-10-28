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
 * Porte de 1er lancement du LLM local (OPP-193). Tant que le modèle n'est pas présent, bloque
 * l'app et propose son téléchargement avec barre de progression ; avertit honnêtement si la RAM
 * est juste/insuffisante. Une fois le modèle prêt, laisse passer vers l'application.
 *
 * Fail-open : si le statut est indéterminable (vieux backend sans la route), on laisse passer
 * plutôt que de bloquer l'app — les fonctions qui exigent le LLM signaleront elles-mêmes l'absence.
 */
export function LlmSetupGate({ children }: { children: ReactNode }) {
  const status = useLlmStatus();

  if (status.isLoading) {
    return <FullScreen>Vérification de l'assistant local…</FullScreen>;
  }
  if (status.isError || !status.data || status.data.model_present) {
    return <>{children}</>;
  }

  return <FirstLaunch status={status.data} onReady={status.refetch} />;
}

function FirstLaunch({
  status,
  onReady,
}: {
  status: NonNullable<ReturnType<typeof useLlmStatus>["data"]>;
  onReady: () => void;
}) {
  const queryClient = useQueryClient();
  const start = useStartLlmSetup();
  // Un téléchargement déjà en cours au (re)montage (ex. rechargement) : on reprend le sondage.
  const [downloading, setDownloading] = useState(status.setup.state === "running");
  const progress = useLlmSetupProgress(downloading);
  const setup = progress.data ?? status.setup;

  // Dès que le modèle est prêt, on réinterroge le statut : `model_present` passe à vrai et la
  // porte s'ouvre vers l'app.
  useEffect(() => {
    if (setup.state === "done") {
      queryClient.invalidateQueries({ queryKey: systemKeys.llmStatus });
      onReady();
    }
  }, [setup.state, queryClient, onReady]);

  if (!status.ollama_reachable) {
    return (
      <FullScreen>
        <Card>
          <h1 className="text-lg font-bold tracking-tight text-ink">Assistant local indisponible</h1>
          <p className="mt-2 text-sm text-ink-muted">
            Le moteur Ollama est injoignable. Vérifie qu'il est démarré, puis réessaie.
          </p>
          <button onClick={() => onReady()} className={primaryButton}>
            Réessayer
          </button>
        </Card>
      </FullScreen>
    );
  }

  const percent = Math.round(setup.fraction * 100);
  const failed = setup.state === "failed";

  return (
    <FullScreen>
      <Card>
        <h1 className="text-lg font-bold tracking-tight text-ink">Préparation d'Opportune</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Opportune utilise un modèle d'IA <strong>local</strong> (
          <code className="rounded bg-ink/5 px-1 py-0.5">{status.model}</code>, ~3 Go). Il
          s'installe une seule fois, puis tout tourne sur ta machine, sans cloud.
        </p>

        <MemoryNotice memory={status.memory} />

        {downloading && !failed && (
          <div className="mt-5">
            <div className="h-2 w-full overflow-hidden rounded-full bg-ink/10">
              <div
                className="h-full rounded-full bg-brand transition-all"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-ink-muted">
              Téléchargement du modèle… {percent}%
            </p>
          </div>
        )}

        {failed && (
          <p className="mt-4 rounded-md bg-danger/10 px-3 py-2 text-sm text-danger">
            Le téléchargement a échoué{setup.error ? ` : ${setup.error}` : ""}.
          </p>
        )}

        {(!downloading || failed) && (
          <button
            onClick={() => {
              setDownloading(true);
              start.mutate();
            }}
            disabled={start.isPending}
            className={primaryButton}
          >
            {failed ? "Réessayer le téléchargement" : "Installer le modèle"}
          </button>
        )}
      </Card>
    </FullScreen>
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

  const tone =
    memory.level === "insufficient"
      ? "bg-danger/10 text-danger"
      : "bg-warning/15 text-warning-text";

  return <p className={`mt-4 rounded-md px-3 py-2 text-sm ${tone}`}>{text}</p>;
}

const primaryButton =
  "mt-5 rounded-md bg-ink px-4 py-2 text-sm font-medium text-on-brand transition-colors hover:bg-ink/90 disabled:opacity-60";

function FullScreen({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 text-center text-sm text-ink-muted">
      {children}
    </div>
  );
}

function Card({ children }: { children: ReactNode }) {
  return (
    <div className="w-full max-w-md rounded-xl border border-border bg-surface-raised p-6 text-left shadow-sm">
      {children}
    </div>
  );
}
