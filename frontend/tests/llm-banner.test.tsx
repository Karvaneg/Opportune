import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LlmBanner } from "../src/components/LlmBanner";

/** Statut /system/llm/status, surchargeable par cas. */
function status(overrides: Record<string, unknown> = {}) {
  return {
    ollama_reachable: true,
    model: "ministral-3:3b",
    model_present: false,
    memory: { level: "ok", total_gb: 16, recommended_gb: 8, minimum_gb: 4 },
    setup: { state: "idle", status: "", fraction: 0, error: null },
    ...overrides,
  };
}

/** fetch factice : /system/llm/status renvoie `body`. */
function stubStatus(body: unknown) {
  const ok = (b: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => ok(String(url).includes("/system/llm/status") ? body : {})),
  );
}

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LlmBanner />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LlmBanner (OPP-193/195)", () => {
  it("n'affiche rien quand le modèle est présent", async () => {
    stubStatus(status({ model_present: true }));

    const { container } = renderBanner();
    // Laisse le temps au sondage de se résoudre avant d'affirmer l'absence de bandeau.
    await Promise.resolve();

    expect(container).toBeEmptyDOMElement();
  });

  it("propose l'installation du modèle, sans bloquer, en invitant à explorer la Démo", async () => {
    stubStatus(status({ model_present: false }));

    renderBanner();

    expect(await screen.findByText("Installer le modèle")).toBeInTheDocument();
    expect(screen.getByText(/ministral-3:3b/)).toBeInTheDocument();
    expect(screen.getByText(/explorer l'espace Démo/)).toBeInTheDocument();
  });

  it("avertit honnêtement quand la RAM est insuffisante", async () => {
    stubStatus(
      status({
        model_present: false,
        memory: { level: "insufficient", total_gb: 2, recommended_gb: 8, minimum_gb: 4 },
      }),
    );

    renderBanner();

    expect(await screen.findByText(/sous le minimum conseillé/)).toBeInTheDocument();
  });

  it("signale quand le moteur local est injoignable", async () => {
    stubStatus(status({ model_present: false, ollama_reachable: false }));

    renderBanner();

    expect(await screen.findByText(/Assistant local injoignable/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
  });
});
