import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CockpitPage } from "../src/pages/CockpitPage";
import { AuthProvider } from "../src/auth/AuthContext";
import { TargetCandidateProvider } from "../src/auth/useTargetCandidate";

const STATS = { a_etudier: 3, a_postuler: 2, postule: 5, offres_total: 12 };

const PROFILE = {
  id: "cand-1", name: "Marie", skills: ["React"], contract_type: "CDI",
  location: null, languages: [], total_experience_years: null,
};

const ACTIVITY = {
  items: [
    { type: "decision", at: "2026-09-06T00:00:00+00:00", label: "Candidature approuvée — Dev Python",
      target_kind: "recommendation", target_id: "cand-1:off-a" },
    { type: "offer", at: "2026-09-01T00:00:00+00:00", label: "Offre ajoutée — Lead Java",
      target_kind: "offer", target_id: "off-c" },
  ],
};

/** fetch factice : /me (reviewer, 1 candidat), /stats, /activity, POST /offers pour l'ajout. */
function stubFetch(statsBody: unknown = STATS, role = "reviewer", activityBody: unknown = ACTIVITY) {
  const calls: { url: string; body?: unknown }[] = [];
  const ok = (b: unknown) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      // Source du ciblage (OPP-184) : une recherche « cand-1 » dans le périmètre.
      if (s.includes("/searches")) return ok({ items: [{ id: "cand-1", label: "Marie" }] });
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/activity")) return ok(activityBody);
      if (s.includes("/profile")) return ok(PROFILE);
      // Profil établi (OPP-177) : au moins un run existe → le guide « Nouveau profil » reste masqué
      // et n'interfère pas avec ces scénarios (sinon il doublerait le bouton « Lancer une analyse »).
      if (s.includes("/runs")) return ok({ items: [], page: 1, page_size: 20, total: 1, total_pages: 1 });
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
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <TargetCandidateProvider>
          <MemoryRouter initialEntries={["/"]}>
            <Routes>
              <Route path="/" element={<CockpitPage />} />
              <Route path="/offres" element={<OffersProbe />} />
              <Route path="/recommendations/:id" element={<div>FICHE RECO</div>} />
            </Routes>
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

describe("CockpitPage (OPP-164)", () => {
  it("affiche les trois compteurs depuis GET /stats + le total du pool", async () => {
    stubFetch();
    renderCockpit();

    // Les libellés et leurs valeurs.
    expect(await screen.findByText("À étudier")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("À postuler")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Postulées")).toBeInTheDocument();
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

  it("affiche la « Dernière activité » et lie chaque événement à sa cible (OPP-165)", async () => {
    stubFetch();
    renderCockpit();

    expect(await screen.findByText("Dernières activités")).toBeInTheDocument();
    // Un événement de décision pointe vers la fiche de recommandation (attendre le chargement).
    await userEvent.click(await screen.findByText("Candidature approuvée — Dev Python"));
    expect(await screen.findByText("FICHE RECO")).toBeInTheDocument();
  });

  it("flux d'activité vide → message dédié", async () => {
    stubFetch(STATS, "reviewer", { items: [] });
    renderCockpit();

    expect(await screen.findByText("Aucune activité récente.")).toBeInTheDocument();
  });
});
