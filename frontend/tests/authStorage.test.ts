import { afterEach, describe, expect, it, vi } from "vitest";
import { purgeLegacyLocalToken, sessionAuthStorage } from "../src/auth/authStorage";

const TOKEN_KEY = "opportune.auth.token";

afterEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("sessionAuthStorage", () => {
  it("écrit, relit et efface le jeton via sessionStorage", () => {
    expect(sessionAuthStorage.get()).toBeNull();

    sessionAuthStorage.set("tok");
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe("tok");
    expect(sessionAuthStorage.get()).toBe("tok");

    sessionAuthStorage.clear();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(sessionAuthStorage.get()).toBeNull();
  });

  it("ne persiste PAS dans localStorage (session liée à l'onglet, OPP-102)", () => {
    sessionAuthStorage.set("tok");
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("tolère un stockage indisponible sans lever (navigation privée, SSR)", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("stockage indisponible");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("stockage indisponible");
    });

    expect(() => sessionAuthStorage.set("tok")).not.toThrow();
    expect(sessionAuthStorage.get()).toBeNull();
  });
});

describe("purgeLegacyLocalToken (migration OPP-102)", () => {
  it("supprime le jeton hérité de localStorage sans toucher à sessionStorage", () => {
    localStorage.setItem(TOKEN_KEY, "vieux-jeton");
    sessionAuthStorage.set("session-courante");

    purgeLegacyLocalToken();

    expect(localStorage.getItem(TOKEN_KEY)).toBeNull(); // secret hérité purgé
    expect(sessionAuthStorage.get()).toBe("session-courante"); // session intacte
  });

  it("est idempotent et ne lève pas en l'absence de jeton hérité", () => {
    expect(() => purgeLegacyLocalToken()).not.toThrow();
    expect(() => purgeLegacyLocalToken()).not.toThrow();
  });
});
