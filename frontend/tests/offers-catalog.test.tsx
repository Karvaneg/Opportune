import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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

/** fetch factice : identité (avec périmètre) sur /me, rescore (ouverture fiche) sinon catalogue. */
function stubFetch(catalogBody: unknown) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      const body = s.includes("/me")
        ? { id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] }
        : s.includes("/rescore")
          ? (calls.push(s), { recommendation_id: "cand-1:b", candidate_id: "cand-1", offer_id: "b" })
          : catalogBody;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
    }),
  );
  return calls;
}

function renderOffers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Routes>
            <Route path="/" element={<OffersPage />} />
            <Route path="/recommendations/:id" element={<div>FICHE RECO</div>} />
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
    // Le titre n'est plus un lien externe : c'est un bouton qui ouvre la fiche interne.
    expect(screen.getByRole("button", { name: "Lead Java" })).toBeInTheDocument();
    // Le lien externe reste accessible en secondaire pour l'offre qui a une URL.
    expect(screen.getByRole("link", { name: /voir sur le site/ })).toHaveAttribute(
      "href",
      "https://initech.example/c",
    );
  });

  it("cliquer une offre l'évalue (rescore) et ouvre sa fiche de recommandation", async () => {
    const calls = stubFetch(CATALOG);
    renderOffers();

    await userEvent.click(await screen.findByRole("button", { name: "Full-stack" }));

    // Rescore ciblé sur le couple candidat/offre → get-or-create de la décision…
    await screen.findByText("FICHE RECO"); // …puis navigation vers la fiche.
    expect(calls.some((u) => u.includes("/candidates/cand-1/offers/b/rescore"))).toBe(true);
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
