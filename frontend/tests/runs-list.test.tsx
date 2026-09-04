import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunsListPage } from "../src/pages/RunsListPage";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const PAGE = {
  items: [
    { run_id: "r-a2", candidate_id: "cand-1", executed_at: "2026-09-03T10:00:00+00:00", evaluation_count: 2, error_count: 1 },
    { run_id: "r-a1", candidate_id: "cand-1", executed_at: "2026-09-01T10:00:00+00:00", evaluation_count: 1, error_count: 0 },
  ],
  page: 1,
  page_size: 20,
  total: 2,
  total_pages: 1,
};

/** fetch factice : identité sur /me, page de runs sinon. */
function stubFetch(runsBody: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve(
            String(url).includes("/me") ? { id: "u", role: "reviewer", owned_count: 1 } : runsBody,
          ),
      } as Response),
    ),
  );
}

/** fetch factice paginé : sert la page demandée via `?page=` (identité sur /me). */
function stubPaginatedFetch(pages: Record<number, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      const page = Number(new URL(s, "http://x").searchParams.get("page") ?? "1");
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve(
            s.includes("/me") ? { id: "u", role: "reviewer", owned_count: 1 } : pages[page],
          ),
      } as Response);
    }),
  );
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <RunsListPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("RunsListPage", () => {
  it("liste les runs avec un lien vers le détail et le total", async () => {
    stubFetch(PAGE);
    renderList();

    expect(await screen.findByText("r-a2")).toBeInTheDocument();
    // La ligne est un lien vers /runs/:runId.
    expect(screen.getByText("r-a2").closest("a")).toHaveAttribute("href", "/runs/r-a2");
    expect(screen.getByText("r-a1")).toBeInTheDocument();
    expect(screen.getByText(/2 au total/)).toBeInTheDocument();
  });

  it("affiche un état vide quand le périmètre n'a aucun run", async () => {
    stubFetch({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 });
    renderList();

    expect(await screen.findByText(/Aucun run dans votre périmètre/)).toBeInTheDocument();
  });

  it("navigue vers la page suivante au clic sur « Suivant »", async () => {
    stubPaginatedFetch({
      1: {
        items: [{ run_id: "r-p1", candidate_id: "cand-1", executed_at: "2026-09-03T10:00:00+00:00", evaluation_count: 1, error_count: 0 }],
        page: 1,
        page_size: 20,
        total: 2,
        total_pages: 2,
      },
      2: {
        items: [{ run_id: "r-p2", candidate_id: "cand-1", executed_at: "2026-09-02T10:00:00+00:00", evaluation_count: 1, error_count: 0 }],
        page: 2,
        page_size: 20,
        total: 2,
        total_pages: 2,
      },
    });
    renderList();

    expect(await screen.findByText("r-p1")).toBeInTheDocument();
    // Sur la première page, « Précédent » est désactivé.
    expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));

    expect(await screen.findByText("r-p2")).toBeInTheDocument();
    // Sur la dernière page, « Suivant » est désactivé.
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });
});
