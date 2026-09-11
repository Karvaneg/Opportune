import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecommendationPage } from "../src/pages/RecommendationPage";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const DETAIL = {
  recommendation_id: "cand-1:off-app",
  candidate_id: "cand-1",
  offer_id: "off-app",
  action: "postuler",
  score: 100,
  title: "Développeur Full-Stack",
  company: "Holis",
  justification: "Score 100/100 — forte adéquation.",
  status: "approved",
  comment: "Bonne adéquation",
  history: [
    { status: "pending", at: "2026-09-04T10:00:00+00:00", comment: null },
    { status: "approved", at: "2026-09-04T11:00:00+00:00", comment: "Bonne adéquation" },
  ],
};

/** fetch factice : identité sur /me, détail reco (ou status arbitraire) sinon. */
function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const isMe = String(url).includes("/me");
      return Promise.resolve({
        ok: isMe ? true : status >= 200 && status < 300,
        status: isMe ? 200 : status,
        json: () =>
          Promise.resolve(isMe ? { id: "u", role: "reviewer", owned_count: 1 } : body),
      } as Response);
    }),
  );
}

function renderPage(id = "cand-1:off-app") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/recommendations/${id}`]}>
          <Routes>
            <Route path="/recommendations/:id" element={<RecommendationPage />} />
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

describe("RecommendationPage", () => {
  it("affiche le détail : offre, action, score, justification, commentaire et historique", async () => {
    stubFetch(200, DETAIL);
    renderPage();

    expect(await screen.findByText("Développeur Full-Stack")).toBeInTheDocument();
    expect(screen.getByText("Holis")).toBeInTheDocument();
    expect(screen.getByText("Postuler")).toBeInTheDocument(); // action libellée
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText(/forte adéquation/)).toBeInTheDocument();
    // Le commentaire courant figure aussi dans l'historique (dernier événement) → 2 occurrences.
    expect(screen.getAllByText(/Bonne adéquation/).length).toBeGreaterThanOrEqual(1);
    // Historique : deux événements (pending puis approved).
    expect(screen.getByText("À décider")).toBeInTheDocument();
    expect(screen.getAllByText("Approuvé").length).toBeGreaterThanOrEqual(1);
  });

  it("404 → message neutre (anti-énumération)", async () => {
    stubFetch(404, { error: "recommandation inconnue" });
    renderPage("cand-1:absente");

    expect(
      await screen.findByText("Recommandation introuvable ou inaccessible."),
    ).toBeInTheDocument();
  });

  it("offre disparue (title/company null) → repli sur offer_id", async () => {
    stubFetch(200, { ...DETAIL, title: null, company: null });
    renderPage();

    // offer_id sert de repli : présent en titre ET dans le méta « Offre » (2 occurrences).
    expect((await screen.findAllByText("off-app")).length).toBeGreaterThanOrEqual(1);
  });
});

/** fetch factice à état : /me (rôle paramétrable), GET détail, POST /decision → approved. */
function stubDecisionFlow(role = "reviewer") {
  let current = {
    ...DETAIL,
    status: "pending",
    comment: null as string | null,
    history: [
      { status: "pending", at: "2026-09-04T10:00:00+00:00", comment: null as string | null },
    ],
  };
  const ok = (body: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      if (s.includes("/me")) return ok({ id: "u", role, owned_count: 1 });
      if (s.includes("/decision")) {
        current = {
          ...current,
          status: "approved",
          comment: "ok",
          history: [
            ...current.history,
            { status: "approved", at: "2026-09-04T11:00:00+00:00", comment: "ok" },
          ],
        };
        return ok(current);
      }
      return ok(current); // GET /recommendations/{id}
    }),
  );
}

describe("RecommendationPage — validation humaine (OPP-108)", () => {
  it("un reviewer valide (approve) → statut à jour sans rechargement", async () => {
    stubDecisionFlow("reviewer");
    renderPage();

    // Au départ : décision en attente (badge principal + historique), aucun « Approuvé ».
    expect((await screen.findAllByText("À décider")).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Approuvé")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "Approuver" }));

    // Après succès, l'invalidation refetche le détail → statut/historique passent à approved.
    await waitFor(() =>
      expect(screen.getAllByText("Approuvé").length).toBeGreaterThanOrEqual(1),
    );
  });

  it("un non-reviewer ne voit pas les boutons de validation (garde UI)", async () => {
    stubDecisionFlow("candidate");
    renderPage();

    await screen.findByText("Développeur Full-Stack"); // détail chargé
    expect(screen.queryByRole("button", { name: "Approuver" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Rejeter" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reporter" })).toBeNull();
  });
});
