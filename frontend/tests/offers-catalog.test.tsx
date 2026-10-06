import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OffersPage } from "../src/pages/OffersPage";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const CATALOG = {
  items: [
    { id: "c", title: "Lead Java", company: "Initech", location: "Lyon",
      contract_type: "Freelance", seniority: "Lead", source: "indeed",
      url: "https://initech.example/c", created_at: "2026-03-01T00:00:00+00:00",
      score: 0, action: "ignorer" },
    { id: "b", title: "Full-stack", company: "Globex", location: "Paris",
      contract_type: "CDI", seniority: "Senior", source: "indeed",
      url: "", created_at: "2026-02-01T00:00:00+00:00", score: 78, action: "a_etudier" },
  ],
  page: 1,
  page_size: 20,
  total: 2,
  total_pages: 1,
};

/** fetch factice : identité (avec périmètre) sur /me, catalogue sinon. */
function stubFetch(catalogBody: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve(
            String(url).includes("/me")
              ? { id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] }
              : catalogBody,
          ),
      } as Response),
    ),
  );
}

function renderOffers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <OffersPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("OffersPage", () => {
  it("liste les offres du catalogue avec leur score de match", async () => {
    stubFetch(CATALOG);
    renderOffers();

    expect(await screen.findByText("Lead Java")).toBeInTheDocument();
    expect(screen.getByText("Full-stack")).toBeInTheDocument();
    // Score annoté pour le candidat ciblé, coloré selon la bande renvoyée par le serveur
    // (ambre pour `a_etudier`, gris pour `ignorer`) — pas de seuil recalculé côté client.
    expect(screen.getByText("0/100")).toBeInTheDocument();
    expect(screen.getByText("78/100")).toHaveClass("bg-amber-100");
    expect(screen.getByText("0/100")).toHaveClass("bg-slate-100");
    expect(screen.getByText(/2 au total/)).toBeInTheDocument();
    // L'offre avec une URL expose un lien externe sur son titre.
    expect(screen.getByText("Lead Java").closest("a")).toHaveAttribute(
      "href",
      "https://initech.example/c",
    );
  });

  it("affiche un état vide quand le catalogue est vide", async () => {
    stubFetch({ items: [], page: 1, page_size: 20, total: 0, total_pages: 0 });
    renderOffers();

    expect(await screen.findByText(/Aucune offre dans le catalogue/)).toBeInTheDocument();
  });

  it("affiche un tiret quand aucun score n'est disponible", async () => {
    stubFetch({
      items: [
        { id: "x", title: "Sans score", company: "Acme", location: "Paris",
          contract_type: "CDI", seniority: "Senior", source: "collée",
          url: "", created_at: "2026-01-01T00:00:00+00:00", score: null, action: null },
      ],
      page: 1, page_size: 20, total: 1, total_pages: 1,
    });
    renderOffers();

    expect(await screen.findByText("Sans score")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
