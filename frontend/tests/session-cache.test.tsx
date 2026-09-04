import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { AuthProvider } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

// Stockage en mémoire (pas de localStorage réel dans le test).
function memoryStorage(initial: string | null = null): AuthStorage {
  let value = initial;
  return {
    get: () => value,
    set: (t) => {
      value = t;
    },
    clear: () => {
      value = null;
    },
  };
}

const RUN = { run_id: "r1", candidate_id: "c1", executed_at: "2026-01-01", evaluations: [], errors: [] };
const RECOS = { run_id: "r1", items: [], page: 1, page_size: 20, total: 0, total_pages: 0 };
const ME = { id: "u", role: "reviewer", owned_count: 1 };

/** fetch factice : 200 (forme selon l'endpoint) pour le bon jeton, 401 sinon. */
function tokenAwareFetch() {
  return vi.fn((url: string, init?: RequestInit) => {
    const auth = (init?.headers as Record<string, string>)?.Authorization;
    const ok = auth === "Bearer good";
    const payload = url.includes("/me")
      ? ME
      : url.includes("/recommendations")
        ? RECOS
        : RUN;
    return Promise.resolve({
      ok,
      status: ok ? 200 : 401,
      json: () => Promise.resolve(ok ? payload : { error: "authentification requise" }),
    } as Response);
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("réinitialisation du cache entre sessions", () => {
  it("un login avec un jeton invalide ne réaffiche pas les données de la session précédente", async () => {
    vi.stubGlobal("fetch", tokenAwareFetch());
    const user = userEvent.setup();

    // App porte son propre <BrowserRouter> : on positionne la route via l'historique jsdom.
    window.history.pushState({}, "", "/runs/r1");

    // Session 1 : bon jeton pré-chargé, on est sur /runs/r1.
    render(
      <AuthProvider storage={memoryStorage("good")}>
        <App />
      </AuthProvider>,
    );
    // Le candidat du run chargé s'affiche.
    expect(await screen.findByText("c1")).toBeInTheDocument();

    // Déconnexion → retour à la barrière de login.
    await user.click(screen.getByRole("button", { name: /déconnexion/i }));
    const field = await screen.findByPlaceholderText(/token/i);

    // Session 2 : jeton invalide → l'API répond 401, aucune donnée cachée ne doit réapparaître.
    await user.type(field, "garbage");
    await user.click(screen.getByRole("button", { name: /continuer/i }));

    // Jeton refusé (/me → 401) : message d'erreur, on reste au login, aucune donnée fantôme.
    expect(await screen.findByText("Jeton invalide.")).toBeInTheDocument();
    expect(screen.queryByText("c1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continuer/i })).toBeInTheDocument();
  });
});
