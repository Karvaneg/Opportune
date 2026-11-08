import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CockpitPage } from "../src/pages/CockpitPage";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";
import { TargetCandidateProvider } from "../src/api/useTargetCandidate";

const STATS = {
  a_etudier: 3, a_postuler: 2, postule: 5, offres_total: 12, entretiens_prevus: 1,
  a_relancer: 4,
};

const SCORING_QUALITY = {
  retained: { count: 0, mean: null, bands: { high: 0, medium: 0, low: 0 } },
  rejected: { count: 0, mean: null, bands: { high: 0, medium: 0, low: 0 } },
  min_per_group: 10, verdict: "insuffisant", gap: null, high_threshold: 80, medium_threshold: 60,
};

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

/** fetch factice : /me (1 candidat), /stats, /activity, POST /offers pour l'ajout. */
function stubFetch(statsBody: unknown = STATS, activityBody: unknown = ACTIVITY) {
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
        return ok({ id: "u", owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/activity")) return ok(activityBody);
      if (s.includes("/profile")) return ok(PROFILE);
      // Profil établi (OPP-177) : au moins un run existe → le guide « Nouveau profil » reste masqué
      // et n'interfère pas avec ces scénarios (sinon il doublerait le bouton « Lancer une analyse »).
      if (s.includes("/runs")) return ok({ items: [], page: 1, page_size: 20, total: 1, total_pages: 1 });
      if (s.includes("/stats")) return ok(statsBody);
      if (s.includes("/scoring-quality")) return ok(SCORING_QUALITY);
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
    <ApiStatusProvider>
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
    </ApiStatusProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CockpitPage (OPP-164)", () => {
  it("affiche les compteurs depuis GET /stats + le total du pool", async () => {
    stubFetch();
    renderCockpit();

    // Les libellés et leurs valeurs.
    expect(await screen.findByText("À étudier")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("À postuler")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Postulées")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    // Entretiens prévus (OPP-223) : 4e carte.
    expect(screen.getByText("Entretiens prévus")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    // À relancer (OPP-235) : 5e carte.
    expect(screen.getByText("À relancer")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText(/12 offre\(s\) au total/)).toBeInTheDocument();
  });

  it("un clic sur « Entretiens prévus » ouvre Offres filtré sur « entretien » (OPP-223)", async () => {
    stubFetch();
    renderCockpit();

    await userEvent.click(await screen.findByRole("button", { name: /Entretiens prévus/ }));
    expect(await screen.findByText(/PAGE OFFRES stage=entretien/)).toBeInTheDocument();
  });

  it("un clic sur « À relancer » ouvre Offres filtré sur « a_relancer » (OPP-235)", async () => {
    stubFetch();
    renderCockpit();

    await userEvent.click(await screen.findByRole("button", { name: /À relancer/ }));

    expect(await screen.findByText(/PAGE OFFRES stage=a_relancer/)).toBeInTheDocument();
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

  it("n'affiche plus « Nouvelle analyse » ni « Ajouter une offre », déplacés sur Offres (OPP-238)", async () => {
    stubFetch();

    renderCockpit();

    await screen.findByText("À étudier");
    expect(screen.queryByText("Nouvelle analyse")).toBeNull();
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
    stubFetch(STATS, { items: [] });
    renderCockpit();

    expect(await screen.findByText("Aucune activité récente.")).toBeInTheDocument();
  });
});
