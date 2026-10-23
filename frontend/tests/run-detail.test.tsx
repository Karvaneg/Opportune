import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunDetailPage } from "../src/pages/RunDetailPage";
import { AuthProvider } from "../src/auth/AuthContext";

function item(id: string) {
  return {
    recommendation_id: id,
    offer_id: id,
    score: 66,
    advisory_status: "pending",
    action: "a_etudier",
    decision_status: "approved",
    title: id,
    company: "Holis",
    justification: "j",
  };
}

/** fetch factice : /me reviewer, détail du run, recommandations paginées (live). */
function stub() {
  const ok = (b: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/recommendations"))
        return ok({
          run_id: "run-1",
          items: [item("off-1"), item("off-2")],
          page: 1,
          page_size: 20,
          total: 2,
          total_pages: 1,
        });
      return ok({
        run_id: "run-1",
        candidate_id: "cand-1",
        executed_at: "2026-09-11T21:14:41+00:00",
        evaluations: [{ offer_id: "off-1" }, { offer_id: "off-2" }],
        errors: [],
      });
    }),
  );
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/runs/run-1"]}>
          <Routes>
            <Route path="/runs/:runId" element={<RunDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("RunDetailPage — clarté (OPP-149)", () => {
  it("affiche métadonnées + une seule liste (live), sans section « Évaluations » figée", async () => {
    stub();
    renderPage();

    // Métadonnées du run (en-tête).
    expect(await screen.findByText("cand-1")).toBeInTheDocument();
    expect(screen.getByText("Offres évaluées")).toBeInTheDocument(); // libellé méta (count)

    // Plus de section figée « Évaluations » : seule « Recommandations » demeure.
    expect(screen.getByText("Recommandations")).toBeInTheDocument();
    expect(screen.queryByText("Évaluations")).toBeNull();

    // Légende des badges (pré-évaluation vs décision).
    expect(screen.getByText(/pré-évaluation/i)).toBeInTheDocument();

    // Chaque offre n'apparaît qu'UNE fois (fin de la duplication).
    expect(await screen.findAllByText("off-1")).toHaveLength(1);
    expect(screen.getAllByText("off-2")).toHaveLength(1);
  });
});
