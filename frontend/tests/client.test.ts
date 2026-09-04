import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiHttpError, apiFetch } from "../src/api/client";

function stubFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("préfixe /api, envoie le Bearer et renvoie le JSON en cas de succès", async () => {
    const fetchMock = stubFetch(200, { run_id: "r1" });
    const data = await apiFetch<{ run_id: string }>("/runs/r1", "tok");

    expect(data).toEqual({ run_id: "r1" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/r1",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok" }),
      }),
    );
  });

  it("404 → message NEUTRE (anti-énumération) avec status préservé", async () => {
    stubFetch(404, { error: "ressource introuvable" });
    await expect(apiFetch("/runs/x", "tok")).rejects.toMatchObject({
      status: 404,
      message: "Run introuvable ou inaccessible.",
    });
  });

  it("401 → ApiHttpError.status = 401 (permet la purge du jeton en amont)", async () => {
    stubFetch(401, { error: "authentification requise" });
    const err = await apiFetch("/runs/x", "tok").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiHttpError);
    expect((err as ApiHttpError).status).toBe(401);
  });

  it("autre erreur → reprend le message { error } du corps", async () => {
    stubFetch(400, { error: "page doit être un entier ≥ 1" });
    await expect(apiFetch("/runs/x/recommendations?page=0", "tok")).rejects.toMatchObject({
      status: 400,
      message: "page doit être un entier ≥ 1",
    });
  });

  it("corps non-JSON sur erreur → message générique de repli", async () => {
    const fn = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });
    vi.stubGlobal("fetch", fn);
    await expect(apiFetch("/runs/x", "tok")).rejects.toMatchObject({
      status: 500,
      message: "Une erreur est survenue.",
    });
  });
});
