import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useApiMutation } from "../src/api/mutations";
import { AuthProvider } from "../src/auth/AuthContext";
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

// AuthProvider revérifie le jeton via /me au montage : on stub un 200 pour l'ignorer.
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

function wrapperWith(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider storage={memoryStorage("good")}>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useApiMutation", () => {
  it("injecte le jeton courant dans mutationFn (jamais à passer par l'appelant)", async () => {
    stubMeOk();
    const mutationFn = vi.fn().mockResolvedValue({ ok: true });
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useApiMutation({ mutationFn }), {
      wrapper: wrapperWith(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({ id: "rec-1" });
    });

    expect(mutationFn).toHaveBeenCalledWith({ id: "rec-1" }, "good");
  });

  it("invalide les clés retournées après un succès", async () => {
    stubMeOk();
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(
      () =>
        useApiMutation<{ ok: boolean }, { runId: string }>({
          mutationFn: async () => ({ ok: true }),
          invalidateKeys: (vars) => [["run", vars.runId]],
        }),
      { wrapper: wrapperWith(queryClient) },
    );

    await act(async () => {
      await result.current.mutateAsync({ runId: "r1" });
    });

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["run", "r1"] }),
    );
  });

  it("n'invalide rien si invalidateKeys est omis", async () => {
    stubMeOk();
    const queryClient = new QueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(
      () => useApiMutation({ mutationFn: async () => ({ ok: true }) }),
      { wrapper: wrapperWith(queryClient) },
    );

    await act(async () => {
      await result.current.mutateAsync(undefined);
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
