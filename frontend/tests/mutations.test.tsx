import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { useApiMutation } from "../src/api/mutations";

function wrapperWith(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useApiMutation", () => {
  it("appelle mutationFn avec les variables (local-first : plus de jeton injecté)", async () => {
    const mutationFn = vi.fn().mockResolvedValue({ ok: true });
    const queryClient = new QueryClient();

    const { result } = renderHook(() => useApiMutation({ mutationFn }), {
      wrapper: wrapperWith(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({ id: "rec-1" });
    });

    expect(mutationFn).toHaveBeenCalledWith({ id: "rec-1" });
  });

  it("invalide les clés retournées après un succès", async () => {
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
