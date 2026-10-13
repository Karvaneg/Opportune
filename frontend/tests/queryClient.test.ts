import { describe, expect, it, vi } from "vitest";
import { ApiHttpError } from "../src/api/client";
import { createAuthAwareQueryClient } from "../src/api/queryClient";

/** Déclenche l'`onError` du cache de requêtes en jouant une query qui rejette. */
async function failingQuery(client: ReturnType<typeof createAuthAwareQueryClient>, error: unknown) {
  await client
    .fetchQuery({ queryKey: ["x", Math.random()], queryFn: () => Promise.reject(error) })
    .catch(() => {});
}

/** Déclenche l'`onError` du cache de mutations en exécutant une mutation qui rejette. */
async function failingMutation(client: ReturnType<typeof createAuthAwareQueryClient>, error: unknown) {
  await client
    .getMutationCache()
    .build(client, { mutationFn: () => Promise.reject(error) })
    .execute(undefined)
    .catch(() => {});
}

describe("createAuthAwareQueryClient", () => {
  it("appelle onAuthExpired sur un 401 en lecture (query)", async () => {
    const onAuthExpired = vi.fn();
    const client = createAuthAwareQueryClient(onAuthExpired);
    await failingQuery(client, new ApiHttpError(401, "expiré", null));
    expect(onAuthExpired).toHaveBeenCalledTimes(1);
  });

  it("appelle onAuthExpired sur un 401 en écriture (mutation) — gap comblé OPP-102", async () => {
    const onAuthExpired = vi.fn();
    const client = createAuthAwareQueryClient(onAuthExpired);
    await failingMutation(client, new ApiHttpError(401, "expiré", null));
    expect(onAuthExpired).toHaveBeenCalledTimes(1);
  });

  it("n'appelle PAS onAuthExpired sur un 403 (rôle insuffisant, pas une expiration)", async () => {
    const onAuthExpired = vi.fn();
    const client = createAuthAwareQueryClient(onAuthExpired);
    await failingQuery(client, new ApiHttpError(403, "interdit", null));
    await failingMutation(client, new ApiHttpError(403, "interdit", null));
    expect(onAuthExpired).not.toHaveBeenCalled();
  });

  it("ignore les erreurs non-HTTP (réseau)", async () => {
    const onAuthExpired = vi.fn();
    const client = createAuthAwareQueryClient(onAuthExpired);
    await failingQuery(client, new Error("réseau"));
    expect(onAuthExpired).not.toHaveBeenCalled();
  });
});
