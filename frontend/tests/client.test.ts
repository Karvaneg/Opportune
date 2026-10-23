import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiHttpError, apiFetch, apiPost } from "../src/api/client";

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
  it("préfixe /api, n'envoie aucun Authorization (local-first) et renvoie le JSON", async () => {
    const fetchMock = stubFetch(200, { run_id: "r1" });
    const data = await apiFetch<{ run_id: string }>("/runs/r1");

    expect(data).toEqual({ run_id: "r1" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/runs/r1");
    expect((init?.headers ?? {}).Authorization).toBeUndefined();
  });

  it("404 → message NEUTRE (anti-énumération) avec status préservé", async () => {
    stubFetch(404, { error: "ressource introuvable" });
    await expect(apiFetch("/runs/x")).rejects.toMatchObject({
      status: 404,
      message: "Run introuvable ou inaccessible.",
    });
  });

  it("erreur HTTP → ApiHttpError avec status préservé", async () => {
    stubFetch(403, { error: "interdit" });
    const err = await apiFetch("/runs/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiHttpError);
    expect((err as ApiHttpError).status).toBe(403);
  });

  it("autre erreur → reprend le message { error } du corps", async () => {
    stubFetch(400, { error: "page doit être un entier ≥ 1" });
    await expect(apiFetch("/runs/x/recommendations?page=0")).rejects.toMatchObject({
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
    await expect(apiFetch("/runs/x")).rejects.toMatchObject({
      status: 500,
      message: "Une erreur est survenue.",
    });
  });
});

describe("apiPost", () => {
  it("POST + corps JSON et Content-Type (sans Authorization), renvoie le JSON", async () => {
    const fetchMock = stubFetch(200, { action_id: "a1", status: "simulated" });
    const data = await apiPost<{ action_id: string }>("/applications/rec-1/confirm", {
      confirm: true,
    });

    expect(data).toEqual({ action_id: "a1", status: "simulated" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/applications/rec-1/confirm",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ confirm: true }),
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      }),
    );
    const [, init] = fetchMock.mock.calls[0];
    expect((init?.headers ?? {}).Authorization).toBeUndefined();
  });

  it("409 → ApiHttpError avec status préservé (ex. candidature sans décision approuvée)", async () => {
    stubFetch(409, { error: "décision approuvée requise" });
    const err = await apiPost("/applications/x/confirm", { confirm: true }).catch(
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(ApiHttpError);
    expect((err as ApiHttpError).status).toBe(409);
    expect((err as ApiHttpError).body).toEqual({ error: "décision approuvée requise" });
  });

  it("corps absent → envoie un objet vide (jamais `undefined` dans le body)", async () => {
    const fetchMock = stubFetch(200, {});
    await apiPost("/x", undefined);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/x",
      expect.objectContaining({ body: "{}" }),
    );
  });
});
