import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CockpitPage } from "../src/pages/CockpitPage";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const STATS = { a_etudier: 3, a_postuler: 2, postule: 5, offres_total: 12 };

/** fetch factice : /me (reviewer, 1 candidat), /stats, POST /offers pour l'ajout. */
function stubFetch(statsBody: unknown = STATS, role = "reviewer") {
  const calls: { url: string; body?: unknown }[] = [];
  const ok = (b: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/stats")) return ok(statsBody);
      if (s.includes("/offers") && init?.method === "POST") {
        calls.push({ url: s, body: JSON.parse(String(init?.body ?? "{}")) });
        return ok({ id: "o1", title: "Data Engineer", company: "Holis" });
      }
      return ok(statsBody);
    }),
  );
  return calls;
}

/** Sonde /offres : révèle l'étape d'entonnoir reçue en query param, pour vérifier la navigation. */
function OffersProbe() {
  const [params] = useSearchParams();
  return <div>PAGE OFFRES stage={params.get("stage")}</div>;
}

/** Monte le cockpit à `/`, avec une route `/offres` sonde pour vérifier la navigation. */
function renderCockpit() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<CockpitPage />} />
            <Route path="/offres" element={<OffersProbe />} />
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

describe("CockpitPage (OPP-164)", () => {
  it("affiche les trois compteurs depuis GET /stats + le total du pool", async () => {
    stubFetch();
    renderCockpit();

    // Les libellés et leurs valeurs.
    expect(await screen.findByText("À étudier")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("À postuler")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Postulé")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText(/12 offre\(s\) au total/)).toBeInTheDocument();
  });

  it("un clic sur « À postuler » ouvre Offres filtré sur cette étape", async () => {
    stubFetch();
    renderCockpit();

    await userEvent.click(await screen.findByRole("button", { name: /À postuler/ }));
    expect(await screen.findByText(/PAGE OFFRES stage=a_postuler/)).toBeInTheDocument();
  });

  it("la carte « Postulé » est cliquable et filtre sur l'étape postulé", async () => {
    stubFetch();
    renderCockpit();

    await userEvent.click(await screen.findByRole("button", { name: /Postulé/ }));
    expect(await screen.findByText(/PAGE OFFRES stage=postule/)).toBeInTheDocument();
  });

  it("propose les raccourcis Lancer une analyse et Ajouter une offre (reviewer)", async () => {
    stubFetch();
    renderCockpit();

    expect(await screen.findByRole("button", { name: "Lancer une analyse" })).toBeInTheDocument();
    expect(screen.getByLabelText("Texte de l'offre")).toBeInTheDocument();
  });

  it("ajoute une offre en collant son texte (POST /offers) depuis le cockpit", async () => {
    const calls = stubFetch();
    renderCockpit();

    await userEvent.type(
      await screen.findByLabelText("Texte de l'offre"),
      "Nous recrutons un Data Engineer",
    );
    await userEvent.click(screen.getByRole("button", { name: "Ajouter l'offre" }));

    expect(await screen.findByText(/Offre ajoutée : Data Engineer/)).toBeInTheDocument();
    const posted = calls.filter((c) => c.url.includes("/offers"));
    expect(posted).toHaveLength(1);
    expect((posted[0].body as { text?: string }).text).toContain("Data Engineer");
  });

  it("cache « Ajouter une offre » à un non-reviewer", async () => {
    stubFetch(STATS, "candidate");
    renderCockpit();

    // Les compteurs restent visibles, mais pas le formulaire d'ajout (reviewer-gated).
    await screen.findByText("À étudier");
    expect(screen.queryByLabelText("Texte de l'offre")).toBeNull();
  });
});
