import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";
import { TargetCandidateProvider } from "../src/api/useTargetCandidate";
import { LaunchRun } from "../src/components/LaunchRun";
import { RecommendationPage } from "../src/pages/RecommendationPage";
import { RunDetailPage } from "../src/pages/RunDetailPage";
import { RunsListPage } from "../src/pages/RunsListPage";

/**
 * Retour depuis une fiche (OPP-240) : Historique → run → recommandation, puis retour à chaque
 * niveau. Chaque liste doit retrouver sa page (et, pour un run, ses filtres).
 */

const DETAIL = {
  recommendation_id: "cand-1:off-1",
  candidate_id: "cand-1",
  offer_id: "off-1",
  action: "postuler",
  score: 80,
  title: "Offre off-1",
  company: "Holis",
  skills: ["React"],
  kind: "emploi",
  url: "",
  created_at: "2026-09-01T08:00:00+00:00",
  justification: "j",
  status: "approved",
  comment: null,
  history: [],
  application: null,
};

/** fetch factice : 3 pages de runs, 3 pages de recos par run, détail d'une reco. */
function stubFetch() {
  const urls: string[] = [];
  const ok = (b: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      urls.push(s);
      const page = Number(new URL(s, "http://x").searchParams.get("page") ?? "1");
      if (s.includes("/searches")) return ok({ items: [{ id: "cand-1", label: "Marie" }] });
      if (s.includes("/me"))
        return ok({ id: "u", owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/profile")) return ok({ id: "cand-1", name: "Marie", skills: ["React"] });
      if (s.includes("/candidates/cand-1/recommendations"))
        return ok({ run_id: "run-9", candidate_id: "cand-1", total: 1, errors: [] });
      if (/\/runs\/[^/?]+\/recommendations/.test(s))
        return ok({
          run_id: "run-2",
          items: [{
            recommendation_id: "cand-1:off-1", offer_id: "off-1", score: 80,
            advisory_status: "approved", action: "postuler", decision_status: "approved",
            title: "Offre off-1", company: "Holis", justification: "j",
          }],
          page, page_size: 20, total: 45, total_pages: 3,
        });
      if (/\/runs\/[^/?]+/.test(s))
        return ok({
          run_id: "run-2", candidate_id: "cand-1", executed_at: "2026-09-11T21:14:41+00:00",
          evaluations: [], errors: [],
        });
      if (s.includes("/runs"))
        return ok({
          items: [{
            run_id: `run-${page}`, candidate_id: "cand-1",
            executed_at: "2026-09-03T10:00:00+00:00", evaluation_count: 1, error_count: 0,
          }],
          page, page_size: 20, total: 45, total_pages: 3,
        });
      return ok(DETAIL); // détail d'une recommandation (et ses sous-ressources)
    }),
  );
  return urls;
}

function renderApp(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ApiStatusProvider>
      <QueryClientProvider client={qc}>
        <TargetCandidateProvider>
          <MemoryRouter initialEntries={[initialPath]}>
            <Routes>
              <Route path="/historique" element={<RunsListPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/recommendations/:id" element={<RecommendationPage />} />
              <Route path="/offres" element={<LaunchRun />} />
            </Routes>
          </MemoryRouter>
        </TargetCandidateProvider>
      </QueryClientProvider>
    </ApiStatusProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Retour vers une liste paginée (OPP-240)", () => {
  it("retour d'une recommandation : le run retrouve sa page et son filtre", async () => {
    const urls = stubFetch();
    renderApp("/runs/run-2");

    await userEvent.selectOptions(await screen.findByLabelText("Filtre décision"), "approved");
    await userEvent.click(await screen.findByRole("button", { name: "Suivant" }));
    await screen.findByText("Page 2 / 3 · 45 au total");
    await userEvent.click(screen.getByRole("link", { name: "Offre off-1" }));
    await userEvent.click(await screen.findByRole("link", { name: /Retour/ }));

    expect(await screen.findByText("Page 2 / 3 · 45 au total")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtre décision")).toHaveValue("approved");
    const lastRecosCall = urls.filter((u) => u.includes("/runs/run-2/recommendations")).at(-1);
    expect(lastRecosCall).toContain("page=2");
    expect(lastRecosCall).toContain("decision_status=approved");
  });

  it("Historique → run → recommandation → retours : l'Historique retrouve sa page", async () => {
    stubFetch();
    renderApp("/historique");
    await screen.findByText("Page 1 / 3 · 45 au total");

    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    await userEvent.click(await screen.findByRole("link", { name: /run-2/ }));
    await userEvent.selectOptions(await screen.findByLabelText("Filtre décision"), "approved");
    await userEvent.click(await screen.findByRole("link", { name: "Offre off-1" }));
    await userEvent.click(await screen.findByRole("link", { name: /Retour/ }));
    await userEvent.click(await screen.findByRole("link", { name: /Changer de run/ }));

    expect(await screen.findByText("Page 2 / 3 · 45 au total")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /run-2/ })).toBeInTheDocument();
  });

  it("run ouvert par son ID depuis l'Historique : le retour ramène à la même page", async () => {
    stubFetch();
    renderApp("/historique?page=2");
    await screen.findByText("Page 2 / 3 · 45 au total");

    await userEvent.type(screen.getByPlaceholderText("run_id…"), "run-7");
    await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));

    expect(await screen.findByRole("link", { name: /Changer de run/ })).toHaveAttribute(
      "href",
      "/historique?page=2",
    );
  });

  it("run lancé depuis Offres : le retour ramène à Offres", async () => {
    stubFetch();
    renderApp("/offres");

    await userEvent.click(await screen.findByRole("button", { name: "Lancer une analyse" }));

    expect(await screen.findByRole("link", { name: /Changer de run/ })).toHaveAttribute(
      "href",
      "/offres",
    );
  });

  it("changer de filtre sur un run revient en page 1", async () => {
    stubFetch();
    renderApp("/runs/run-2?page=2");
    await screen.findByText("Page 2 / 3 · 45 au total");

    await userEvent.selectOptions(screen.getByLabelText("Filtre décision"), "approved");

    expect(await screen.findByText("Page 1 / 3 · 45 au total")).toBeInTheDocument();
  });

  it("accès direct à un run : « Changer de run » mène à l'Historique (OPP-240)", async () => {
    stubFetch();

    renderApp("/runs/run-2");

    expect(await screen.findByRole("link", { name: /Changer de run/ })).toHaveAttribute(
      "href",
      "/historique",
    );
  });

  it("Historique : une page au-delà de la dernière est ramenée à la dernière", async () => {
    stubFetch();

    renderApp("/historique?page=50");

    expect(await screen.findByText("Page 3 / 3 · 45 au total")).toBeInTheDocument();
  });
});
