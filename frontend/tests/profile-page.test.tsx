import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfilePage } from "../src/pages/ProfilePage";
import { AuthProvider } from "../src/auth/AuthContext";
import { TargetCandidateProvider } from "../src/auth/useTargetCandidate";

const PROFILE = {
  id: "cand-1", name: "Marie", skills: ["React"], contract_type: "CDI",
  location: null, languages: [], total_experience_years: null, experiences: [],
};

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/** fetch factice : /searches (périmètre paramétrable, source du ciblage), /me, /profile (figé). */
function stub(candidates: string[], role = "reviewer") {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      if (s.includes("/searches"))
        return ok({ items: candidates.map((id) => ({ id, label: id })) });
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: candidates.length, owned_candidate_ids: candidates });
      if (s.includes("/profile")) return ok(PROFILE);
      return ok({});
    }),
  );
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <TargetCandidateProvider>
          <ProfilePage />
        </TargetCandidateProvider>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ProfilePage", () => {
  it("affiche le profil du candidat ciblé, avec l'import CV placé avant les compétences", async () => {
    stub(["cand-1"]);
    renderPage();

    // Le panneau est monté (compétence du profil visible).
    expect(await screen.findByText("React")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Profil" })).toBeInTheDocument();

    // L'import CV passe désormais AVANT la section Compétences (exigence du repositionnement).
    const cvImport = screen.getByText("Importer un CV (PDF)");
    const skills = screen.getByText("Compétences");
    expect(cvImport.compareDocumentPosition(skills) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("cible la première recherche du périmètre quand il en compte plusieurs (OPP-184)", async () => {
    // Le sélecteur de recherche est désormais global (cf. SearchBar) ; la page affiche le profil
    // de la recherche active, par défaut la première du périmètre.
    stub(["cand-1", "cand-2"]);
    renderPage();

    expect(await screen.findByText("React")).toBeInTheDocument();
  });

  it("affiche un message quand le périmètre est vide", async () => {
    stub([]);
    renderPage();

    expect(await screen.findByText(/Aucune recherche pour le moment/)).toBeInTheDocument();
  });
});
