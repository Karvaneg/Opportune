import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OffersPage } from "../src/pages/OffersPage";
import { funnelStage } from "../src/api/funnel";
import { AuthProvider } from "../src/auth/AuthContext";
import { TargetCandidateProvider } from "../src/auth/useTargetCandidate";
import type { DecisionStatus } from "../src/api/types";

const CATALOG = {
  items: [
    { id: "c", title: "Lead Java", company: "Initech", location: "Lyon",
      contract_type: "Freelance", seniority: "Lead", source: "indeed",
      url: "https://initech.example/c", created_at: "2026-03-01T00:00:00+00:00",
      kind: "emploi", score: 0, action: "ignorer",
      decision_status: "pending", applied: false },        // → à étudier
    { id: "b", title: "Full-stack", company: "Globex", location: "Paris",
      contract_type: "CDI", seniority: "Senior", source: "indeed",
      url: "", created_at: "2026-02-01T00:00:00+00:00", kind: "emploi",
      score: 78, action: "a_etudier",
      decision_status: "approved", applied: false },        // → à postuler
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
      const body = s.includes("/searches")
        ? { items: [{ id: "cand-1", label: "Marie" }] }
        : s.includes("/me")
        ? { id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] }
        : s.includes("/rescore")
          ? (calls.push(s), { recommendation_id: "cand-1:b", candidate_id: "cand-1", offer_id: "b" })
          : catalogBody;
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
    }),
  );
  return calls;
}

function renderOffers(initialPath = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <TargetCandidateProvider>
          <MemoryRouter initialEntries={[initialPath]}>
            <Routes>
              <Route path="/" element={<OffersPage />} />
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

describe("OffersPage", () => {
  it("liste les offres du catalogue avec leur score de match", async () => {
    stubFetch(CATALOG);
    renderOffers();

    // Titre ciblé par rôle : il devient un bouton une fois la recherche active résolue (le
    // sélecteur global passe brièvement par un état vide au montage) — le nœud reste stable.
    expect(await screen.findByRole("button", { name: "Lead Java" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Full-stack" })).toBeInTheDocument();
    // Score annoté pour le candidat ciblé, coloré selon la bande renvoyée par le serveur
    // (warning pour `a_etudier`, neutre pour `ignorer`) — pas de seuil recalculé côté client.
    expect(screen.getByText("0/100")).toBeInTheDocument();
    expect(screen.getByText("78/100")).toHaveClass("bg-warning/15");
    expect(screen.getByText("0/100")).toHaveClass("bg-ink/5");
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
          url: "", created_at: "2026-01-01T00:00:00+00:00", kind: "emploi",
          score: null, action: null, decision_status: null, applied: false },
      ],
      page: 1, page_size: 20, total: 1, total_pages: 1,
    });
    renderOffers();

    expect(await screen.findByRole("button", { name: "Sans score" })).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("badge une formation tout en la gardant cliquable (fiche décidable, OPP-166)", async () => {
    const calls = stubFetch({
      items: [
        { id: "f", title: "Formation ISTQB", company: "Skolae", location: "À distance",
          contract_type: "CDI", seniority: "Débutant", source: "collée",
          url: "https://skolae.example/f", created_at: "2026-01-01T00:00:00+00:00",
          kind: "formation", score: null, action: null,
          decision_status: null, applied: false },
      ],
      page: 1, page_size: 20, total: 1, total_pages: 1,
    });
    renderOffers();

    // Badge « Formation » explicite — pas de 0, pas de tiret ambigu.
    expect(await screen.findByText("Formation")).toBeInTheDocument();
    // Mais le titre reste cliquable : candidater à une formation a du sens → fiche ouvrable.
    const title = screen.getByRole("button", { name: "Formation ISTQB" });
    await userEvent.click(title);
    await screen.findByText("FICHE RECO"); // rescore (get-or-create) puis navigation vers la fiche
    expect(calls.some((u) => u.includes("/candidates/cand-1/offers/f/rescore"))).toBe(true);
  });

  // --- Filtre par étape d'entonnoir, piloté par l'URL (clic sur une carte du cockpit, OPP-164) ---

  it("filtre le catalogue par étape via ?stage= (filtrage serveur) et efface le filtre", async () => {
    // Le serveur filtre tout le pool par étape AVANT pagination : le stub renvoie le
    // sous-ensemble correspondant au param ?stage=, et on vérifie que la requête le porte.
    const urls: string[] = [];
    const ok = (b: unknown) =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const s = String(url);
        if (s.includes("/searches")) return ok({ items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/me"))
          return ok({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        urls.push(s);
        const stage = new URL(s, "http://x").searchParams.get("stage");
        const items = stage
          ? CATALOG.items.filter(
              (o) => funnelStage(o.decision_status as DecisionStatus | null, o.applied) === stage,
            )
          : CATALOG.items;
        return ok({ ...CATALOG, items, total: items.length, total_pages: 1 });
      }),
    );
    // b est « approuvée » → à postuler ; c « pending » → à étudier (indépendant du score algo).
    renderOffers("/?stage=a_postuler");

    expect(await screen.findByRole("button", { name: "Full-stack" })).toBeInTheDocument(); // b (approuvée)
    expect(screen.queryByRole("button", { name: "Lead Java" })).not.toBeInTheDocument(); // c absente du sous-ensemble
    expect(urls.some((u) => u.includes("stage=a_postuler"))).toBe(true); // filtre envoyé au serveur
    // Un chip annonce le filtre actif et offre de l'effacer.
    expect(screen.getByText("Filtré : À postuler")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /effacer le filtre/ }));
    // Filtre levé : la requête repart sans stage, les deux offres réapparaissent.
    expect(await screen.findByRole("button", { name: "Lead Java" })).toBeInTheDocument();
    expect(urls.some((u) => u.includes("/offers") && !u.includes("stage="))).toBe(true);
  });

  // --- Bouton « Récupérer de nouvelles offres » (collecte asynchrone, OPP-170) ---

  // Réponse factice avec statut explicite (202 au démarrage, 200 au sondage).
  const res = (status: number, b: unknown) =>
    Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(b) } as Response);
  const ME = { id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] };
  // Profil renseigné : débloque le bouton de collecte (OPP-219). Les scénarios de collecte
  // supposent un profil déjà constitué.
  const READY_PROFILE = {
    id: "cand-1", name: "Marie", skills: ["React"], contract_type: "CDI",
    location: null, languages: [], total_experience_years: null, experiences: [],
  };
  const noProgress = {
    collected: 0, stored: 0, duplicates: 0, failures: 0, enriched: 0, enriched_recovered: 0,
  };

  it("démarre une collecte (POST /collect → 202) puis sonde et affiche le bilan", async () => {
    const posts: Array<{ url: string; body: unknown }> = [];
    const job = {
      job_id: "job-1", status: "done", error: null,
      progress: { collected: 4, stored: 1, duplicates: 3, failures: 0, enriched: 2, enriched_recovered: 1 },
      report: {
        collected: 4, stored: 1, duplicates: 3, failures: 0, source_error: null,
        enriched: 2, enriched_recovered: 1,
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/collect")) {
          if (options?.method === "POST") {
            posts.push({ url: s, body: JSON.parse(String(options?.body ?? "{}")) });
            return res(202, { job_id: "job-1" }); // démarrage asynchrone
          }
          return res(200, job); // GET /collect/job-1 : sondage, déjà terminé
        }
        return res(200, CATALOG);
      }),
    );
    renderOffers();

    await screen.findByText("Lead Java"); // catalogue chargé
    // Le poste est prérempli (OPP-167) : on le remplace pour vérifier la transmission.
    await userEvent.clear(screen.getByLabelText("Poste recherché"));
    await userEvent.type(screen.getByLabelText("Poste recherché"), "python");
    await userEvent.type(screen.getByLabelText("Lieu de recherche"), "Paris");
    await userEvent.click(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    );

    // Bilan lisible (nouvelles / collectées / doublons) et critères transmis au serveur.
    expect(await screen.findByText(/1 nouvelle offre/)).toBeInTheDocument();
    // Compteurs d'enrichissement visibles quand une offre a été enrichie (OPP-169).
    expect(screen.getByText(/2 enrichies \(1 récupérée\)/)).toBeInTheDocument();
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toEqual({ what: "python", where: "Paris" });
  });

  it("sonde jusqu'à la fin : progression en cours puis bilan final", async () => {
    let getCalls = 0;
    const running = {
      job_id: "job-2", status: "running", error: null, report: null,
      progress: { collected: 2, stored: 1, duplicates: 1, failures: 0, enriched: 0, enriched_recovered: 0 },
    };
    const done = {
      job_id: "job-2", status: "done", error: null,
      progress: { collected: 5, stored: 3, duplicates: 2, failures: 0, enriched: 0, enriched_recovered: 0 },
      report: {
        collected: 5, stored: 3, duplicates: 2, failures: 0, source_error: null,
        enriched: 0, enriched_recovered: 0,
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/collect")) {
          if (options?.method === "POST") return res(202, { job_id: "job-2" });
          // Suivi global (GET /collect sans id, OPP-208) : neutre ici, ne consomme pas la
          // séquence du sondage par id qui pilote l'affichage « Récupération… ».
          if (s.split("?")[0].endsWith("/collect")) return res(200, { job: null });
          getCalls += 1;
          return res(200, getCalls === 1 ? running : done); // 1er sondage en cours, puis terminé
        }
        return res(200, CATALOG);
      }),
    );
    renderOffers();

    await screen.findByText("Lead Java");
    await userEvent.click(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    );

    // Pendant que le job tourne, le bouton reflète l'état « en cours » (la progression
    // détaillée est portée par le bandeau global `CollectionBanner`, hors de cette page — OPP-215)…
    expect(
      await screen.findByRole("button", { name: /Récupération en cours…/ }),
    ).toBeInTheDocument();
    // …puis le bilan final après re-sondage (refetchInterval ~1,5 s).
    expect(
      await screen.findByText(/3 nouvelles offres/, undefined, { timeout: 3000 }),
    ).toBeInTheDocument();
  });

  it("envoie le poste recherché prérempli quand le champ n'est pas modifié", async () => {
    const posts: Array<{ body: { what?: string; where?: string } }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/collect")) {
          if (options?.method === "POST") {
            posts.push({ body: JSON.parse(String(options?.body ?? "{}")) });
            return res(202, { job_id: "job-3" });
          }
          return res(200, {
            job_id: "job-3", status: "done", error: null, progress: noProgress,
            report: { ...noProgress, source_error: null },
          });
        }
        return res(200, CATALOG);
      }),
    );
    renderOffers();

    await screen.findByText("Lead Java");
    await userEvent.click(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    );

    // Défaut métier large, lieu vide → collecte pertinente sans aucune saisie.
    await screen.findByText(/0 nouvelle offre/);
    expect(posts).toHaveLength(1);
    expect(posts[0].body.what).toMatch(/développeur/);
    expect(posts[0].body.where).toBe("");
  });

  it("affiche l'erreur de source quand la collecte échoue côté Adzuna", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/collect")) {
          if (options?.method === "POST") return res(202, { job_id: "job-4" });
          return res(200, {
            job_id: "job-4", status: "done", error: null, progress: noProgress,
            report: {
              ...noProgress,
              source_error: "AdzunaAuthError: identifiants manquants",
            },
          });
        }
        return res(200, CATALOG);
      }),
    );
    renderOffers();

    await screen.findByText("Lead Java");
    await userEvent.click(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    );

    // Une panne de source (job done avec source_error) prime sur les compteurs : on le dit.
    expect(await screen.findByText(/Collecte impossible/)).toBeInTheDocument();
  });

  it("désactive « Récupérer de nouvelles offres » tant que le profil est vierge (OPP-219)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(404, { error: "profil introuvable" }); // vierge
        if (s.includes("/collect")) return res(200, { job: null });
        return res(200, CATALOG);
      }),
    );
    renderOffers();

    await screen.findByText("Lead Java"); // catalogue chargé
    // On attend la résolution du profil (404) via l'invite, puis on vérifie le bouton.
    expect(await screen.findByText(/Ajoute d'abord ton CV/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    ).toBeDisabled();
  });

  it("invite à renseigner les clés Adzuna quand elles manquent, sans bloquer (OPP-195)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/settings/adzuna")) return res(200, { configured: false });
        if (s.includes("/collect")) return res(200, { job: null });
        return res(200, CATALOG);
      }),
    );

    renderOffers();
    const notice = await screen.findByText(/Les clés Adzuna ne sont pas renseignées/);

    expect(notice).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Réglages" })).toHaveAttribute("href", "/reglages");
    // Profil renseigné : l'invite prévient mais ne verrouille pas le bouton (fallback .env possible).
    expect(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    ).toBeEnabled();
  });

  it("désactive la collecte tant que l'assistant local se prépare (OPP-195)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        // Modèle absent, Ollama joignable → la collecte (enrichissement LLM) est désactivée.
        if (s.includes("/system/llm/status")) return res(200, { model_present: false, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/settings/adzuna")) return res(200, { configured: true });
        if (s.includes("/collect")) return res(200, { job: null });
        return res(200, CATALOG);
      }),
    );

    renderOffers();
    await screen.findByText(/L'assistant local se prépare/);

    expect(
      screen.getByRole("button", { name: /Récupérer de nouvelles offres/ }),
    ).toBeDisabled();
  });

  it("n'affiche pas l'invite Adzuna quand les clés sont configurées (OPP-195)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const s = String(url);
        if (s.includes("/searches")) return res(200, { items: [{ id: "cand-1", label: "Marie" }] });
        if (s.includes("/system/llm/status")) return res(200, { model_present: true, ollama_reachable: true });
        if (s.includes("/me")) return res(200, ME);
        if (s.includes("/profile")) return res(200, READY_PROFILE);
        if (s.includes("/settings/adzuna")) return res(200, { configured: true });
        if (s.includes("/collect")) return res(200, { job: null });
        return res(200, CATALOG);
      }),
    );

    renderOffers();
    await screen.findByText("Lead Java");

    expect(screen.queryByText(/Les clés Adzuna ne sont pas renseignées/)).not.toBeInTheDocument();
  });
});
