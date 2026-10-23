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

/** fetch factice : /me (périmètre paramétrable), /profile (profil figé). */
function stub(candidates: string[], role = "reviewer") {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
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

  it("propose un sélecteur de candidat quand le périmètre en compte plusieurs", async () => {
    stub(["cand-1", "cand-2"]);
    renderPage();

    await screen.findByText("React");
    expect(screen.getByLabelText("Candidat pour le profil")).toBeInTheDocument();
  });

  it("ne montre pas de sélecteur pour un périmètre mono-candidat", async () => {
    stub(["cand-1"]);
    renderPage();

    await screen.findByText("React");
    expect(screen.queryByLabelText("Candidat pour le profil")).not.toBeInTheDocument();
  });
});
