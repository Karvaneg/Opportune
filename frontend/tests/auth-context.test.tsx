import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AuthProvider,
  SESSION_EXPIRED_MESSAGE,
  useAuth,
} from "../src/auth/AuthContext";
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

function stubMeOk() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: "u", role: "reviewer", owned_count: 1 }),
    }),
  );
}

function stubMe401() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: "authentification requise" }),
    }),
  );
}

function wrapperWith(storage: AuthStorage) {
  return ({ children }: { children: ReactNode }) => (
    <AuthProvider storage={storage}>{children}</AuthProvider>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AuthContext — fin de session", () => {
  it("expireSession : retour anonyme, jeton purgé, message d'expiration affiché", async () => {
    stubMeOk();
    const storage = memoryStorage("good");
    const { result } = renderHook(() => useAuth(), { wrapper: wrapperWith(storage) });

    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    act(() => result.current.expireSession());

    expect(result.current.status).toBe("anonymous");
    expect(result.current.token).toBeNull();
    expect(result.current.error).toBe(SESSION_EXPIRED_MESSAGE);
    expect(storage.get()).toBeNull(); // jeton purgé du stockage
  });

  it("logout volontaire : retour anonyme SANS message (différencié de l'expiration)", async () => {
    stubMeOk();
    const storage = memoryStorage("good");
    const { result } = renderHook(() => useAuth(), { wrapper: wrapperWith(storage) });

    await waitFor(() => expect(result.current.status).toBe("authenticated"));

    act(() => result.current.logout());

    expect(result.current.status).toBe("anonymous");
    expect(result.current.error).toBeNull();
    expect(storage.get()).toBeNull();
  });

  it("un login efface le message d'expiration de la session précédente", async () => {
    stubMeOk();
    const storage = memoryStorage("good");
    const { result } = renderHook(() => useAuth(), { wrapper: wrapperWith(storage) });

    await waitFor(() => expect(result.current.status).toBe("authenticated"));
    act(() => result.current.expireSession());
    expect(result.current.error).toBe(SESSION_EXPIRED_MESSAGE);

    await act(async () => {
      await result.current.login("good");
    });

    expect(result.current.status).toBe("authenticated");
    expect(result.current.error).toBeNull();
  });

  it("jeton stocké refusé au démarrage (/me 401) : anonyme AVEC message d'expiration", async () => {
    stubMe401();
    const storage = memoryStorage("stale");
    const { result } = renderHook(() => useAuth(), { wrapper: wrapperWith(storage) });

    await waitFor(() => expect(result.current.status).toBe("anonymous"));
    expect(result.current.token).toBeNull();
    expect(result.current.error).toBe(SESSION_EXPIRED_MESSAGE);
    expect(storage.get()).toBeNull(); // jeton périmé purgé du stockage
  });
});
