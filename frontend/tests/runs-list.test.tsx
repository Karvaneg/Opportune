import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RunsListPage } from "../src/pages/RunsListPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { TargetCandidateProvider } from "../src/auth/useTargetCandidate";

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
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <TargetCandidateProvider>
          <MemoryRouter>
            <RunsListPage />
          </MemoryRouter>
        </TargetCandidateProvider>
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

  it("lance un run pour le candidat du périmètre (POST /candidates/{id}/recommendations)", async () => {
    const calls: string[] = [];
    const okJson = (b: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const s = String(url);
        if (s.includes("/me"))
          return okJson({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        if (s.includes("/candidates/") && init?.method === "POST") {
          calls.push(s);
          return okJson({ run_id: "run-new", items: [], total: 0, errors: [] });
        }
        return okJson(PAGE); // GET /runs
      }),
    );
    renderList();

    await screen.findByText("r-a2"); // liste chargée
    await userEvent.click(screen.getByRole("button", { name: "Lancer une analyse" }));

    await waitFor(() =>
      expect(calls.some((u) => u.includes("/candidates/cand-1/recommendations"))).toBe(true),
    );
  });

  it("run sans nouvelle offre (total 0) : message dédié au lieu d'un run vide (OPP-150)", async () => {
    const okJson = (b: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const s = String(url);
        if (s.includes("/me"))
          return okJson({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        if (s.includes("/candidates/") && init?.method === "POST")
          return okJson({ run_id: "run-empty", items: [], total: 0, errors: [] });
        return okJson(PAGE); // GET /runs
      }),
    );
    renderList();

    await screen.findByText("r-a2");
    await userEvent.click(screen.getByRole("button", { name: "Lancer une analyse" }));

    expect(await screen.findByText("Aucune nouvelle offre à évaluer.")).toBeInTheDocument();
  });

  it("run avec erreurs par offre (total 0 mais errors) : pas le message « aucune offre » (OPP-150)", async () => {
    // total 0 n'implique pas « rien à faire » : des offres ont échoué. Le run est bien
    // persisté côté back → on n'affiche pas le message trompeur (et le front y navigue).
    const okJson = (b: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const s = String(url);
        if (s.includes("/me"))
          return okJson({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        if (s.includes("/candidates/") && init?.method === "POST")
          return okJson({ run_id: "run-ko", items: [], total: 0, errors: ["off-x: boom"] });
        return okJson(PAGE); // GET /runs
      }),
    );
    renderList();

    await screen.findByText("r-a2");
    await userEvent.click(screen.getByRole("button", { name: "Lancer une analyse" }));

    await waitFor(() =>
      expect(screen.queryByText("Aucune nouvelle offre à évaluer.")).toBeNull(),
    );
  });

  it("supprime un run après confirmation explicite (reviewer)", async () => {
    let deleted = false;
    const okJson = (b: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const s = String(url);
        if (s.includes("/me"))
          return okJson({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        if (s.includes("/runs/") && init?.method === "DELETE") {
          deleted = true;
          return okJson({ deleted: "r-a2" });
        }
        const items = deleted ? PAGE.items.filter((i) => i.run_id !== "r-a2") : PAGE.items;
        return okJson({ ...PAGE, items, total: items.length }); // GET /runs
      }),
    );
    renderList();

    await screen.findByText("r-a2");
    // Premier clic : demande de confirmation (ne supprime pas).
    await userEvent.click(screen.getByRole("button", { name: "Supprimer le run r-a2" }));
    expect(deleted).toBe(false);
    // Confirmation explicite → DELETE → la ligne disparaît après invalidation.
    await userEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    await waitFor(() => expect(screen.queryByText("r-a2")).toBeNull());
    expect(screen.getByText("r-a1")).toBeInTheDocument();
  });

  it("affiche l'erreur si la suppression échoue et conserve la ligne", async () => {
    const okJson = (b: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const s = String(url);
        if (s.includes("/me"))
          return okJson({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        if (s.includes("/runs/") && init?.method === "DELETE")
          // 403 : le message est neutralisé par `messageFor` côté client.
          return Promise.resolve({
            ok: false,
            status: 403,
            json: () => Promise.resolve({ error: "rôle reviewer requis" }),
          } as Response);
        return okJson(PAGE); // GET /runs
      }),
    );
    renderList();

    await screen.findByText("r-a2");
    await userEvent.click(screen.getByRole("button", { name: "Supprimer le run r-a2" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirmer" }));
    // Échec → message affiché, ligne toujours là, retour au bouton « Supprimer ».
    expect(await screen.findByRole("alert")).toHaveTextContent("Accès refusé");
    expect(screen.getByText("r-a2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Supprimer le run r-a2" })).toBeInTheDocument();
  });

  // L'ajout d'offre a été déplacé de « Runs » vers « Offres » (OPP-161) ; sa couverture vit
  // désormais dans offers-catalog.test.tsx.

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
