import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LlmSetupGate } from "../src/components/LlmSetupGate";

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

function renderGate() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LlmSetupGate>
        <div>APPLICATION</div>
      </LlmSetupGate>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LlmSetupGate (OPP-193)", () => {
  it("laisse passer vers l'app quand le modèle est présent", async () => {
    stubStatus(status({ model_present: true }));

    renderGate();

    expect(await screen.findByText("APPLICATION")).toBeInTheDocument();
  });

  it("propose l'installation du modèle quand il est absent", async () => {
    stubStatus(status({ model_present: false }));

    renderGate();

    expect(await screen.findByText("Installer le modèle")).toBeInTheDocument();
    expect(screen.getByText(/ministral-3:3b/)).toBeInTheDocument();
    expect(screen.queryByText("APPLICATION")).not.toBeInTheDocument();
  });

  it("avertit honnêtement quand la RAM est insuffisante", async () => {
    stubStatus(
      status({
        model_present: false,
        memory: { level: "insufficient", total_gb: 2, recommended_gb: 8, minimum_gb: 4 },
      }),
    );

    renderGate();

    expect(await screen.findByText(/sous le minimum conseillé/)).toBeInTheDocument();
  });

  it("signale quand le moteur local est injoignable", async () => {
    stubStatus(status({ model_present: false, ollama_reachable: false }));

    renderGate();

    expect(await screen.findByText("Assistant local indisponible")).toBeInTheDocument();
  });
});
