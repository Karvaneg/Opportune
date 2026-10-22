import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewProfileGuide } from "../src/components/NewProfileGuide";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";
import type { CandidateStats } from "../src/api/types";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

const notFound = () =>
  Promise.resolve({
    ok: false,
    status: 404,
    json: () => Promise.resolve({ error: "profil introuvable" }),
  } as Response);

const EMPTY_PROFILE = {
  id: "cand-1", name: "Marie", skills: [], contract_type: "CDI",
  location: null, languages: [], total_experience_years: null, experiences: [],
};
const FILLED_PROFILE = { ...EMPTY_PROFILE, skills: ["React"] };

const runsPage = (total: number) => ({
  items: [], page: 1, page_size: 20, total, total_pages: total > 0 ? 1 : 0,
});

const NO_STATS: CandidateStats = { a_etudier: 0, a_postuler: 0, postule: 0, offres_total: 0 };
const WITH_OFFERS: CandidateStats = { ...NO_STATS, offres_total: 12 };

/**
 * fetch factice paramétrable : /me (rôle), /profile (vierge, rempli, ou **404** = candidat sans
 * profil encore), /runs (compte de runs). `profile: null` ⇒ 404.
 */
function stubFetch({
  profile,
  runsTotal,
  role = "reviewer",
}: {
  profile: unknown;
  runsTotal: number;
  role?: string;
}) {
  const fetchMock = vi.fn((url: string) => {
    const s = String(url);
    if (s.includes("/me"))
      return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
    if (s.includes("/runs")) return ok(runsPage(runsTotal));
    if (s.includes("/profile")) return profile === null ? notFound() : ok(profile);
    return ok({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderGuide(stats: CandidateStats) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<NewProfileGuide candidateId="cand-1" stats={stats} />} />
            <Route path="/offres" element={<div>PAGE OFFRES</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("NewProfileGuide (OPP-177)", () => {
  it("profil vierge : propose les trois étapes à faire", async () => {
    stubFetch({ profile: EMPTY_PROFILE, runsTotal: 0 });
    renderGuide(NO_STATS);

    expect(await screen.findByText("Nouveau profil")).toBeInTheDocument();
    expect(screen.getByText("Ajouter votre CV")).toBeInTheDocument();
    expect(screen.getByText("Récupérer de nouvelles offres")).toBeInTheDocument();
    expect(screen.getByText("Lancer une analyse")).toBeInTheDocument();
    // Les trois actions sont offertes (navigation guidée).
    expect(screen.getByRole("button", { name: "Ajouter mon CV" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Récupérer des offres" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Lancer l'analyse" })).toBeInTheDocument();
  });

  it("étape faite : un CV présent coche l'étape 1 (plus de bouton)", async () => {
    stubFetch({ profile: FILLED_PROFILE, runsTotal: 0 });
    renderGuide(NO_STATS);

    // L'étape 2 devient l'action en cours une fois le profil chargé.
    expect(await screen.findByRole("link", { name: "Récupérer des offres" })).toBeInTheDocument();
    // L'étape 1 est faite → son bouton disparaît, mais l'intitulé reste (coché).
    expect(screen.queryByRole("button", { name: "Ajouter mon CV" })).toBeNull();
    expect(screen.getByText("Ajouter votre CV")).toBeInTheDocument();
  });

  it("le bouton « Récupérer des offres » navigue vers /offres", async () => {
    stubFetch({ profile: EMPTY_PROFILE, runsTotal: 0 });
    renderGuide(NO_STATS);

    await userEvent.click(await screen.findByRole("link", { name: "Récupérer des offres" }));
    expect(await screen.findByText("PAGE OFFRES")).toBeInTheDocument();
  });

  it("boucle complète (CV + offres + run) : le guide ne s'affiche pas", async () => {
    const fetchMock = stubFetch({ profile: FILLED_PROFILE, runsTotal: 2 });
    renderGuide(WITH_OFFERS);

    // On attend que profil ET runs soient chargés, puis on vérifie l'absence du guide.
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("/runs"))).toBe(true);
      expect(urls.some((u) => u.includes("/profile"))).toBe(true);
    });
    expect(screen.queryByText("Nouveau profil")).toBeNull();
  });

  it("candidat sans profil encore (404) : le guide s'affiche quand même, étape 1 à faire", async () => {
    // Le cas « nouveau profil » par excellence : aucun profil en base → GET /profile renvoie 404.
    // Le guide doit s'afficher (et non disparaître) pour inviter à importer un CV.
    stubFetch({ profile: null, runsTotal: 0 });
    renderGuide(NO_STATS);

    expect(await screen.findByText("Nouveau profil")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter mon CV" })).toBeInTheDocument();
  });

  it("étape « analyse » : les runs interrogés sont scopés au candidat ciblé", async () => {
    const fetchMock = stubFetch({ profile: EMPTY_PROFILE, runsTotal: 0 });
    renderGuide(NO_STATS);

    await screen.findByText("Nouveau profil");
    const runsUrl = fetchMock.mock.calls
      .map((c) => String(c[0]))
      .find((u) => u.includes("/runs"));
    expect(runsUrl).toContain("candidate_id=cand-1");
  });

  it("non-reviewer : le guide ne s'affiche pas (actions de curation inaccessibles)", async () => {
    const fetchMock = stubFetch({ profile: EMPTY_PROFILE, runsTotal: 0, role: "viewer" });
    renderGuide(NO_STATS);

    // On attend que l'identité (/me) soit résolue, puis on vérifie l'absence du guide.
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("/me"))).toBe(true);
    });
    expect(screen.queryByText("Nouveau profil")).toBeNull();
  });
});
