import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunRecommendations } from "../src/components/RunRecommendations";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

function item(id: string, decision_status = "pending") {
  return {
    recommendation_id: id,
    offer_id: id,
    score: 80,
    advisory_status: "approved",
    action: "postuler",
    decision_status,
    title: id,
    company: "Acme",
    justification: "j",
  };
}

const ok = (body: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);

/** fetch factice filtrable : /me reviewer ; la liste dépend de `decision_status`. */
function stubFilterableFetch() {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      if (s.includes("/me")) return ok({ id: "u", role: "reviewer", owned_count: 1 });
      calls.push(s);
      const decision = new URL(s, "http://x").searchParams.get("decision_status");
      if (decision === "approved") {
        return ok({
          run_id: "r1",
          items: [item("off-1", "approved")],
          page: 1,
          page_size: 20,
          total: 1,
          total_pages: 1,
        });
      }
      return ok({
        run_id: "r1",
        items: [item("off-1"), item("off-2")],
        page: 1,
        page_size: 20,
        total: 2,
        total_pages: 1,
      });
    }),
  );
  return calls;
}

function renderRecommendations() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <RunRecommendations runId="r1" />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("RunRecommendations — filtres de statut (OPP-109)", () => {
  it("filtrer par decision_status recharge la liste filtrée et recalcule le total", async () => {
    const calls = stubFilterableFetch();
    renderRecommendations();

    // Sans filtre : 2 items, total 2.
    expect(await screen.findByText("off-2")).toBeInTheDocument();
    expect(screen.getByText(/2 au total/)).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Filtre décision"), "approved");

    // Après filtre : off-2 disparaît, total recalculé à 1.
    await waitFor(() => expect(screen.queryByText("off-2")).toBeNull());
    expect(screen.getByText("off-1")).toBeInTheDocument();
    expect(screen.getByText(/1 au total/)).toBeInTheDocument();

    // La requête filtrée porte bien le query param du contrat back.
    expect(calls.some((u) => u.includes("decision_status=approved"))).toBe(true);
  });

  it("combine advisory_status et decision_status dans la même requête", async () => {
    const calls = stubFilterableFetch();
    renderRecommendations();
    await screen.findByText("off-1");

    await userEvent.selectOptions(screen.getByLabelText("Filtre pré-évaluation"), "approved");
    await userEvent.selectOptions(screen.getByLabelText("Filtre décision"), "approved");

    await waitFor(() =>
      expect(
        calls.some(
          (u) => u.includes("advisory_status=approved") && u.includes("decision_status=approved"),
        ),
      ).toBe(true),
    );
  });

  it("les filtres n'exposent que des valeurs valides du contrat", async () => {
    stubFilterableFetch();
    renderRecommendations();
    await screen.findByText("off-1");

    // Le select décision propose « Toutes » + exactement les 4 statuts de validation.
    const decision = screen.getByLabelText("Filtre décision") as HTMLSelectElement;
    const values = Array.from(decision.options).map((o) => o.value);
    expect(values).toEqual(["", "pending", "approved", "rejected", "deferred"]);
  });
});
