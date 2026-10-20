import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfilePanel } from "../src/components/ProfilePanel";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

function memoryStorage(initial: string | null): AuthStorage {
  let value = initial;
  return { get: () => value, set: (t) => { value = t; }, clear: () => { value = null; } };
}

const PROFILE = {
  id: "cand-1", name: "Marie", skills: ["React", "Node.js"], contract_type: "CDI",
  location: null, languages: [], total_experience_years: null,
};

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/** fetch factice **stateful** : le PUT /profile persiste les skills que le GET renverra ensuite
 * (comme le vrai back, pour que le refetch post-édition reflète la mise à jour). */
function stubFetch(role = "reviewer") {
  const puts: Array<{ skills: string[] }> = [];
  let current = { ...PROFILE };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/profile")) {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init?.body ?? "{}"));
          puts.push(body);
          current = { ...current, skills: body.skills };
          return ok(current);
        }
        return ok(current);
      }
      return ok(current);
    }),
  );
  return puts;
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider storage={memoryStorage("good")}>
      <QueryClientProvider client={qc}>
        <ProfilePanel candidateId="cand-1" />
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ProfilePanel (OPP-158)", () => {
  it("affiche les compétences du profil", async () => {
    stubFetch();
    renderPanel();
    expect(await screen.findByText("React")).toBeInTheDocument();
    expect(screen.getByText("Node.js")).toBeInTheDocument();
  });

  it("ajoute une compétence et l'enregistre (PUT avec la liste complète)", async () => {
    const puts = stubFetch("reviewer");
    renderPanel();
    await screen.findByText("React");

    await userEvent.type(screen.getByLabelText("Ajouter une compétence"), "Agile");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Enregistrer les compétences/ }),
    );

    expect(await screen.findByText("Compétences à jour.")).toBeInTheDocument();
    expect(puts).toHaveLength(1);
    expect(puts[0].skills).toEqual(["React", "Node.js", "Agile"]);
  });

  it("retire une compétence avant d'enregistrer", async () => {
    const puts = stubFetch("reviewer");
    renderPanel();
    await screen.findByText("React");

    await userEvent.click(screen.getByRole("button", { name: "Retirer Node.js" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Enregistrer les compétences/ }),
    );

    await screen.findByText("Compétences à jour.");
    expect(puts[0].skills).toEqual(["React"]);
  });

  it("n'ajoute pas un doublon (insensible à la casse)", async () => {
    stubFetch("reviewer");
    renderPanel();
    await screen.findByText("React");

    await userEvent.type(screen.getByLabelText("Ajouter une compétence"), "react");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter" }));

    // Toujours une seule puce « React » (le doublon « react » est ignoré).
    const list = screen.getByRole("list");
    expect(within(list).getAllByText(/^React$/i)).toHaveLength(1);
    // Rien à enregistrer puisque la liste n'a pas changé.
    expect(
      screen.getByRole("button", { name: /Enregistrer les compétences/ }),
    ).toBeDisabled();
  });

  it("lecture seule pour un non-reviewer (pas de contrôle d'édition)", async () => {
    stubFetch("viewer");
    renderPanel();
    await screen.findByText("React");

    expect(screen.queryByLabelText("Ajouter une compétence")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Enregistrer les compétences/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retirer React" })).not.toBeInTheDocument();
  });
});
