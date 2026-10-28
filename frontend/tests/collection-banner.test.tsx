import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CollectionBanner } from "../src/components/CollectionBanner";

/** Stub `GET /collect` → `{ job }` (le hook global `useActiveCollectJob`). */
function stubActiveCollect(job: unknown) {
  const fetchMock = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ job }),
    } as Response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderBanner() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CollectionBanner />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("CollectionBanner (OPP-208)", () => {
  it("affiche un indicateur persistant quand une collecte tourne", async () => {
    stubActiveCollect({
      job_id: "j1",
      status: "running",
      progress: {
        collected: 5,
        stored: 3,
        duplicates: 2,
        failures: 0,
        enriched: 0,
        enriched_recovered: 0,
      },
      report: null,
      error: null,
      cancel_requested: false,
    });
    const { container } = renderBanner();

    // Lien « Voir » vers la page Offres : nœud stable, preuve que le bandeau est rendu.
    expect(await screen.findByRole("link", { name: "Voir" })).toHaveAttribute("href", "/offres");
    expect(container.textContent).toContain("Collecte d'offres en cours");
    expect(container.textContent).toContain("5 collectées");
    expect(container.textContent).toContain("3 nouvelles");
    expect(screen.getByRole("button", { name: "Arrêter" })).toBeEnabled();
  });

  it("déclenche l'annulation au clic sur « Arrêter » (OPP-209)", async () => {
    const runningJob = {
      job_id: "j1",
      status: "running",
      progress: {
        collected: 2,
        stored: 1,
        duplicates: 0,
        failures: 0,
        enriched: 0,
        enriched_recovered: 0,
      },
      report: null,
      error: null,
      cancel_requested: false,
    };
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        calls.push(`${options?.method ?? "GET"} ${String(url)}`);
        const body = String(url).includes("/cancel") ? { status: "cancelling" } : { job: runningJob };
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
      }),
    );
    renderBanner();

    await userEvent.click(await screen.findByRole("button", { name: "Arrêter" }));
    await waitFor(() =>
      expect(calls.some((c) => c.startsWith("POST") && c.includes("/collect/j1/cancel"))).toBe(true),
    );
  });

  it("explique le délai quand l'arrêt est pris en compte (OPP-215)", async () => {
    // cancel_requested = l'arrêt coopératif est posé mais l'offre en cours se termine encore :
    // le bandeau doit l'expliquer (et non laisser croire à un blocage), bouton désactivé.
    stubActiveCollect({
      job_id: "j1",
      status: "running",
      progress: {
        collected: 3,
        stored: 2,
        duplicates: 1,
        failures: 0,
        enriched: 0,
        enriched_recovered: 0,
      },
      report: null,
      error: null,
      cancel_requested: true,
    });
    const { container } = renderBanner();

    await screen.findByRole("link", { name: "Voir" });
    expect(container.textContent).toContain("Arrêt pris en compte");
    expect(container.textContent).toContain("l'offre en cours se termine");
    expect(screen.getByRole("button", { name: "Arrêt demandé…" })).toBeDisabled();
  });

  it("ne rend rien quand aucune collecte n'est active", async () => {
    const fetchMock = stubActiveCollect(null);
    renderBanner();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Voir" })).toBeNull();
  });
});
