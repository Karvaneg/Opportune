import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SearchBar } from "../src/components/SearchBar";
import { AuthProvider } from "../src/auth/AuthContext";
import { TargetCandidateProvider } from "../src/auth/useTargetCandidate";
import type { Search } from "../src/api/types";

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/**
 * fetch factice **avec état** : une liste de recherches mutable, pour que POST/PUT se reflètent
 * dans le GET /searches suivant (invalidation React Query). `role` pilote le gating reviewer via /me.
 */
function stubFetch(initial: Search[], role = "reviewer") {
  const searches = [...initial];
  const posted: unknown[] = [];
  const put: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      const method = init?.method ?? "GET";
      if (s.includes("/searches") && method === "POST") {
        const { label } = JSON.parse(String(init?.body ?? "{}"));
        posted.push({ label });
        const created = { id: `search-${searches.length + 1}`, label };
        searches.push(created);
        return ok(created);
      }
      if (s.includes("/searches/") && method === "PUT") {
        const id = decodeURIComponent(s.split("/searches/")[1]);
        const { label } = JSON.parse(String(init?.body ?? "{}"));
        put.push({ id, label });
        const row = searches.find((x) => x.id === id);
        if (row) row.label = label;
        return ok({ id, label });
      }
      // Copie à chaque GET : renvoyer la même référence mutée masquerait le changement à
      // React Query (structural sharing) — la vraie API renvoie un tableau neuf à chaque appel.
      if (s.includes("/searches")) return ok({ items: [...searches] });
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: searches.length, owned_candidate_ids: [] });
      return ok({});
    }),
  );
  return { posted, put };
}

function renderBar() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <TargetCandidateProvider>
          <SearchBar />
        </TargetCandidateProvider>
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("SearchBar (OPP-184)", () => {
  it("liste les recherches par libellé et permet d'en changer", async () => {
    stubFetch([
      { id: "cand-1", label: "Data Analyst" },
      { id: "cand-2", label: "Product Manager" },
    ]);
    renderBar();

    const select = (await screen.findByRole("combobox", {
      name: "Recherche active",
    })) as HTMLSelectElement;
    // Les options portent les libellés, et la 1ʳᵉ recherche est active par défaut.
    expect(within(select).getByRole("option", { name: "Data Analyst" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "Product Manager" })).toBeInTheDocument();
    expect(select.value).toBe("cand-1");

    await userEvent.selectOptions(select, "cand-2");
    expect(select.value).toBe("cand-2");
  });

  it("affiche l'id technique à défaut de libellé", async () => {
    stubFetch([{ id: "cand-x", label: "" }]);
    renderBar();

    const select = (await screen.findByRole("combobox", { name: "Recherche active" }));
    expect(within(select).getByRole("option", { name: "cand-x" })).toBeInTheDocument();
  });

  it("crée une recherche nommée (POST /searches) et bascule dessus", async () => {
    const { posted } = stubFetch([{ id: "cand-1", label: "Data Analyst" }]);
    renderBar();

    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle recherche" }));
    await userEvent.type(screen.getByLabelText("Nom de la recherche"), "Data Engineer");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    // POST transmis, puis la nouvelle recherche devient l'option active après réinvalidation.
    await waitFor(() => expect(posted).toEqual([{ label: "Data Engineer" }]));
    const select = (await screen.findByRole("combobox", {
      name: "Recherche active",
    })) as HTMLSelectElement;
    expect(within(select).getByRole("option", { name: "Data Engineer" })).toBeInTheDocument();
    // La bascule se fixe une fois le refetch de /searches arrivé (le nouvel id entre au périmètre).
    await waitFor(() => expect(select.value).toBe("search-2"));
  });

  it("renomme la recherche active (PUT /searches/{id})", async () => {
    const { put } = stubFetch([{ id: "cand-1", label: "Ancien" }]);
    renderBar();

    await userEvent.click(await screen.findByRole("button", { name: "Renommer" }));
    const input = screen.getByLabelText("Nom de la recherche");
    expect(input).toHaveValue("Ancien"); // pré-rempli avec le libellé courant
    await userEvent.clear(input);
    await userEvent.type(input, "Nouveau");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(put).toEqual([{ id: "cand-1", label: "Nouveau" }]));
    const select = await screen.findByRole("combobox", { name: "Recherche active" });
    expect(within(select).getByRole("option", { name: "Nouveau" })).toBeInTheDocument();
  });

  it("cache créer / renommer à un non-reviewer, mais garde la bascule", async () => {
    stubFetch([{ id: "cand-1", label: "Data Analyst" }], "candidate");
    renderBar();

    expect(await screen.findByRole("combobox", { name: "Recherche active" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nouvelle recherche" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Renommer" })).toBeNull();
  });

  it("signale l'échec de GET /searches au lieu de paraître vide", async () => {
    // API HS sur /searches : sans surface d'erreur, toute l'app semblerait avoir un périmètre
    // vide. On doit afficher l'erreur, pas un silence (cf. revue OPP-184).
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const s = String(url);
        if (s.includes("/searches"))
          return Promise.resolve({
            ok: false,
            status: 500,
            json: () => Promise.resolve({ error: "Oups" }),
          } as Response);
        if (s.includes("/me"))
          return ok({ id: "u", role: "reviewer", owned_count: 0, owned_candidate_ids: [] });
        return ok({});
      }),
    );
    renderBar();

    expect(await screen.findByText("Oups")).toBeInTheDocument();
    expect(screen.queryByText("Aucune recherche.")).toBeNull();
  });

  it("périmètre vide : un reviewer peut amorcer une première recherche", async () => {
    const { posted } = stubFetch([]);
    renderBar();

    await userEvent.click(await screen.findByRole("button", { name: "Nouvelle recherche" }));
    await userEvent.type(screen.getByLabelText("Nom de la recherche"), "Première");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => expect(posted).toEqual([{ label: "Première" }]));
    expect(
      await screen.findByRole("option", { name: "Première" }),
    ).toBeInTheDocument();
  });
});
