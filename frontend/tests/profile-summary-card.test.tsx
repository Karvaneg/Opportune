import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfileSummaryCard } from "../src/components/ProfileSummaryCard";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const PROFILE = {
  id: "cand-1", name: "Marie", skills: ["React", "Node.js"], contract_type: "CDI",
  location: null, languages: [], total_experience_years: null, experiences: [{}, {}],
};

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

const notFound = () =>
  Promise.resolve({
    ok: false,
    status: 404,
    json: () => Promise.resolve({ error: "profil introuvable" }),
  } as Response);

/** fetch factice : /me (identité), /profile (profil, ou **404** = candidat sans profil). */
function stub(profile: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/profile")) return profile === null ? notFound() : ok(profile);
      return ok({});
    }),
  );
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ProfileSummaryCard candidateId="cand-1" />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ProfileSummaryCard", () => {
  it("résume le profil (nom, contrat, volumes) et renvoie vers la page Profil", async () => {
    stub(PROFILE);
    renderCard();

    expect(
      await screen.findByText(/Marie · CDI · 2 compétences · 2 expériences/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir" })).toHaveAttribute("href", "/profil");
  });

  it("accorde le singulier sur un profil à une seule compétence / expérience", async () => {
    stub({ ...PROFILE, skills: ["React"], experiences: [{}] });
    renderCard();

    expect(await screen.findByText(/1 compétence · 1 expérience/)).toBeInTheDocument();
  });

  it("profil non renseigné (404) : invite à le compléter plutôt que de signaler une erreur", async () => {
    stub(null);
    renderCard();

    expect(await screen.findByText(/Profil non renseigné/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Compléter" })).toHaveAttribute("href", "/profil");
  });
});
