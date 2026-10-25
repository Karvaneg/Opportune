import { render, screen, waitFor } from "@testing-library/react";
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
    });
    const { container } = renderBanner();

    // Lien « Voir » vers la page Offres : nœud stable, preuve que le bandeau est rendu.
    expect(await screen.findByRole("link", { name: "Voir" })).toHaveAttribute("href", "/offres");
    expect(container.textContent).toContain("Collecte d'offres en cours");
    expect(container.textContent).toContain("5 collectées");
    expect(container.textContent).toContain("3 nouvelles");
  });

  it("ne rend rien quand aucune collecte n'est active", async () => {
    const fetchMock = stubActiveCollect(null);
    renderBanner();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: "Voir" })).toBeNull();
  });
});
