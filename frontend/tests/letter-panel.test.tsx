import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecommendationPage } from "../src/pages/RecommendationPage";
import { AuthProvider } from "../src/auth/AuthContext";

const DETAIL = {
  recommendation_id: "cand-1:off-app",
  candidate_id: "cand-1",
  offer_id: "off-app",
  action: "postuler",
  score: 100,
  title: "Développeur Full-Stack",
  company: "Holis",
  skills: [],
  justification: "Score 100/100.",
  status: "approved",
  comment: null,
  history: [],
};

const AI_LETTER = {
  recommendation_id: "cand-1:off-app",
  body: "Madame, Monsieur, je vous adresse ma candidature avec un grand intérêt pour ce poste.",
  source: "ai",
  model: "ministral-3:3b",
  created_at: "t0",
  updated_at: "t0",
};

type LetterState = typeof AI_LETTER | null;
type Call = { method: string; body: { regenerate?: boolean; body?: string } | null };

/** fetch factice à état : /me (rôle), GET détail reco, et CRUD lettre sur `/letter`. */
function stubLetterFlow({
  role = "reviewer",
  initial = null as LetterState,
  llm = { model_present: true, ollama_reachable: true },
} = {}) {
  let letter: LetterState = initial;
  const calls: Call[] = [];
  const ok = (body: unknown, status = 200) =>
    Promise.resolve({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    } as Response);

  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      const method = init?.method ?? "GET";
      if (s.includes("/me")) return ok({ id: "u", role, owned_count: 1 });
      if (s.includes("/system/llm/status")) return ok(llm);
      if (s.includes("/letter")) {
        const body = init?.body ? JSON.parse(String(init.body)) : null;
        calls.push({ method, body });
        if (method === "GET") return letter ? ok(letter) : ok({ error: "introuvable" }, 404);
        if (method === "POST") {
          letter = { ...AI_LETTER };
          return ok(letter, 201);
        }
        if (method === "PUT") {
          letter = { ...AI_LETTER, body: body.body, source: "human", model: "" };
          return ok(letter);
        }
        if (method === "DELETE") {
          letter = null;
          return ok({ deleted: "cand-1:off-app" });
        }
      }
      return ok(DETAIL); // GET /recommendations/{id}
    }),
  );
  return { calls };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/recommendations/cand-1:off-app"]}>
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

describe("LetterPanel (OPP-147)", () => {
  it("aucune lettre (404) → bouton Générer, puis la lettre générée s'affiche", async () => {
    stubLetterFlow({ initial: null });
    renderPage();

    const generate = await screen.findByRole("button", { name: "Générer la lettre" });
    await userEvent.click(generate);

    expect(await screen.findByText(/j'adresse ma candidature|adresse ma candidature/)).toBeInTheDocument();
    expect(screen.getByText("Générée par l'IA")).toBeInTheDocument();
  });

  it("édition : Éditer → modifier → Enregistrer envoie un PUT et passe en « Éditée à la main »", async () => {
    const { calls } = stubLetterFlow({ initial: { ...AI_LETTER } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
    const textarea = screen.getByLabelText("Corps de la lettre");
    await userEvent.clear(textarea);
    await userEvent.type(textarea, "Version corrigée à la main par la candidate, bien assez longue.");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(screen.getByText("Éditée à la main")).toBeInTheDocument());
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body?.body).toContain("Version corrigée");
  });

  it("régénérer demande confirmation puis envoie { regenerate: true }", async () => {
    const { calls } = stubLetterFlow({
      initial: { ...AI_LETTER, source: "human", model: "" },
    });
    renderPage();

    // Le panneau affiche bien une lettre éditée à la main au départ.
    expect(await screen.findByText("Éditée à la main")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Régénérer" }));

    // La régénération ne part PAS tant que l'humain n'a pas confirmé dans la modale.
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    const dialog = screen.getByRole("dialog", { name: "Confirmer la régénération" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Régénérer" }));

    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body?.regenerate).toBe(true);
    // Après régénération, la lettre repasse « Générée par l'IA ».
    await waitFor(() => expect(screen.getByText("Générée par l'IA")).toBeInTheDocument());
  });

  it("supprimer (après confirmation) repasse à l'état « aucune lettre »", async () => {
    const { calls } = stubLetterFlow({ initial: { ...AI_LETTER } });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
    const dialog = screen.getByRole("dialog", { name: "Confirmer la suppression" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));

    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(await screen.findByRole("button", { name: "Générer la lettre" })).toBeInTheDocument();
    // Le refetch post-suppression renvoie 404 ; React Query garde la `data` périmée, donc on
    // vérifie que l'ancien corps (et ses actions) ne subsistent PAS à côté de « Générer ».
    expect(screen.queryByText(/adresse ma candidature/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Éditer" })).toBeNull();
  });

  it("désactive la génération tant que l'assistant local se prépare (OPP-195)", async () => {
    stubLetterFlow({ initial: null, llm: { model_present: false, ollama_reachable: true } });

    renderPage();
    await screen.findByText(/L'assistant local se prépare/);

    expect(screen.getByRole("button", { name: "Générer la lettre" })).toBeDisabled();
  });

  it("laisse consulter une lettre déjà écrite même sans assistant local (OPP-195)", async () => {
    stubLetterFlow({
      initial: { ...AI_LETTER },
      llm: { model_present: false, ollama_reachable: false },
    });

    renderPage();

    // Le corps de la lettre reste lisible ; seule la régénération est verrouillée.
    expect(await screen.findByText(/adresse ma candidature/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Régénérer" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Éditer" })).toBeEnabled();
  });

  it("un non-reviewer ne voit pas le panneau lettre (garde UI)", async () => {
    stubLetterFlow({ role: "candidate", initial: { ...AI_LETTER } });
    renderPage();

    await screen.findByText("Développeur Full-Stack"); // détail chargé
    expect(screen.queryByText("Lettre de motivation")).toBeNull();
  });
});
