import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { AuthProvider, SESSION_EXPIRED_MESSAGE } from "../src/auth/AuthContext";
import type { AuthStorage } from "../src/auth/authStorage";

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

const ME = { id: "u", role: "reviewer", owned_count: 1 };

/**
 * fetch factice simulant une **expiration en cours de session** : la revérification du
 * jeton au démarrage (`GET /me`) réussit (200, on entre authentifié), mais toute autre
 * requête — ici le chargement des runs — répond 401 (jeton expiré entre-temps).
 */
function meOkThenExpired() {
  return vi.fn((url: string) => {
    const ok = url.includes("/me");
    return Promise.resolve({
      ok,
      status: ok ? 200 : 401,
      json: () => Promise.resolve(ok ? ME : { error: "authentification requise" }),
    } as Response);
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("expiration de session en cours d'usage", () => {
  it("un 401 sur une requête renvoie à la barrière avec le message d'expiration", async () => {
    vi.stubGlobal("fetch", meOkThenExpired());

    render(
      <AuthProvider storage={memoryStorage("good")}>
        <App />
      </AuthProvider>,
    );

    // Le 401 du chargement des runs déclenche l'auto-logout : retour à la barrière de
    // login, avec le message expliquant l'expiration (pas un largage silencieux).
    expect(await screen.findByText(SESSION_EXPIRED_MESSAGE)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /continuer/i })).toBeInTheDocument();
  });
});
