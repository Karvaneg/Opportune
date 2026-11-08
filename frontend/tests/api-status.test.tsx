import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatusProvider, useApiStatus } from "../src/api/ApiStatusContext";

const ME = { id: "moi", owned_count: 1, owned_candidate_ids: ["cand-1"] };

function stubMeOk() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(ME),
    }),
  );
}

/** `/me` en échec réseau : l'API est injoignable (serveur non lancé). */
function stubMeDown() {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("réseau")));
}

function wrapper({ children }: { children: ReactNode }) {
  return <ApiStatusProvider>{children}</ApiStatusProvider>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ApiStatusContext : amorçage local (OPP-181)", () => {
  it("GET /me réussit → statut ready, sans jeton", async () => {
    stubMeOk();
    const { result } = renderHook(() => useApiStatus(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe("ready"));

    // Aucun en-tête Authorization n'est envoyé (local-first).
    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers ?? {}).Authorization).toBeUndefined();
  });

  it("API injoignable → statut error (pas de login)", async () => {
    stubMeDown();
    const { result } = renderHook(() => useApiStatus(), { wrapper });

    await waitFor(() => expect(result.current.status).toBe("error"));
  });

  it("retry relance GET /me et récupère une API revenue", async () => {
    stubMeDown();
    const { result } = renderHook(() => useApiStatus(), { wrapper });
    await waitFor(() => expect(result.current.status).toBe("error"));

    // L'API redevient joignable, puis on réessaie.
    stubMeOk();
    act(() => result.current.retry());

    await waitFor(() => expect(result.current.status).toBe("ready"));
  });
});
