import type { ReactNode } from "react";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, apiPost, setApiSpace } from "../src/api/client";
import { createQueryClient } from "../src/api/queryClient";
import { SpaceProvider, useSpace } from "../src/space/SpaceContext";
import { WelcomeScreen } from "../src/space/WelcomeScreen";
import { DemoBanner } from "../src/space/DemoBanner";

function stubFetch(body: unknown = {}) {
  const fn = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function spaceHeaderOf(fetchMock: ReturnType<typeof vi.fn>): unknown {
  const [, init] = fetchMock.mock.calls[0];
  return (init?.headers ?? {})["X-Opportune-Space"];
}

afterEach(() => {
  setApiSpace(null);
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("client — en-tête d'espace X-Opportune-Space (OPP-182)", () => {
  it("n'envoie pas l'en-tête tant qu'aucun espace n'est choisi (back = mine par défaut)", async () => {
    const fetchMock = stubFetch();
    await apiFetch("/me");
    expect(spaceHeaderOf(fetchMock)).toBeUndefined();
  });

  it("GET porte l'espace actif", async () => {
    setApiSpace("demo");
    const fetchMock = stubFetch();
    await apiFetch("/me");
    expect(spaceHeaderOf(fetchMock)).toBe("demo");
  });

  it("POST porte aussi l'espace actif", async () => {
    setApiSpace("mine");
    const fetchMock = stubFetch();
    await apiPost("/candidates/c/recommendations", {});
    expect(spaceHeaderOf(fetchMock)).toBe("mine");
  });
});

describe("WelcomeScreen (OPP-182)", () => {
  it("propose Mon espace et Démo ; le clic remonte le choix", async () => {
    const onChoose = vi.fn();
    render(<WelcomeScreen onChoose={onChoose} />);

    expect(screen.getByRole("button", { name: /Mon espace/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Démo/ }));
    expect(onChoose).toHaveBeenCalledWith("demo");
  });
});

describe("SpaceProvider (OPP-182)", () => {
  const wrapper = ({ children }: { children: ReactNode }) => <SpaceProvider>{children}</SpaceProvider>;

  it("chooseSpace pose l'espace sur les requêtes et le mémorise ; resetSpace l'oublie", async () => {
    const { result } = renderHook(() => useSpace(), { wrapper });
    expect(result.current.space).toBeNull();

    act(() => result.current.chooseSpace("demo"));
    expect(result.current.space).toBe("demo");
    expect(sessionStorage.getItem("opportune.space")).toBe("demo");

    const fetchMock = stubFetch();
    await apiFetch("/me");
    expect(spaceHeaderOf(fetchMock)).toBe("demo");

    act(() => result.current.resetSpace());
    expect(result.current.space).toBeNull();
    expect(sessionStorage.getItem("opportune.space")).toBeNull();
  });

  it("réhydrate l'espace choisi depuis sessionStorage au montage", () => {
    sessionStorage.setItem("opportune.space", "mine");
    const { result } = renderHook(() => useSpace(), { wrapper });
    expect(result.current.space).toBe("mine");
  });
});

describe("DemoBanner — repartir de zéro / restaurer (OPP-182)", () => {
  function renderBanner() {
    const client = createQueryClient();
    return render(
      <QueryClientProvider client={client}>
        <DemoBanner />
      </QueryClientProvider>,
    );
  }

  it("« Repartir de zéro » confirmé appelle POST /demo/reset", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    const fetchMock = stubFetch({ status: "reset" });
    renderBanner();

    await userEvent.click(screen.getByRole("button", { name: /Repartir de zéro/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/demo/reset");
    expect(init?.method).toBe("POST");
  });

  it("« Repartir de zéro » annulé (confirm refusé) n'appelle rien", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const fetchMock = stubFetch({});
    renderBanner();

    await userEvent.click(screen.getByRole("button", { name: /Repartir de zéro/ }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("« Restaurer l'exemple » appelle POST /demo/restore", async () => {
    const fetchMock = stubFetch({ status: "restored" });
    renderBanner();

    await userEvent.click(screen.getByRole("button", { name: /Restaurer l'exemple/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/demo/restore");
  });

  it("purge le cache (resetQueries) après la commande, pas un simple invalidate", async () => {
    // Après un reset, le profil démo est supprimé → GET /profile 404 ; un invalidate garderait
    // la donnée périmée (profil fantôme → « Ajouter votre CV » barré à tort). resetQueries purge.
    const client = createQueryClient();
    const resetSpy = vi.spyOn(client, "resetQueries");
    stubFetch({ status: "restored" });
    render(
      <QueryClientProvider client={client}>
        <DemoBanner />
      </QueryClientProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: /Restaurer l'exemple/ }));
    await waitFor(() => expect(resetSpy).toHaveBeenCalled());
  });
});
