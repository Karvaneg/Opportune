import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AdzunaSettings } from "../src/components/AdzunaSettings";
import { AuthProvider } from "../src/auth/AuthContext";

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/** fetch factice **stateful** : le PUT /settings/adzuna bascule l'état « configuré » que le GET
 * renverra ensuite (comme le vrai back, pour vérifier le refetch après enregistrement). */
function stubSettings(role = "reviewer", configured = false) {
  const puts: Array<Record<string, unknown>> = [];
  let state = configured;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/settings/adzuna")) {
        if (init?.method === "PUT") {
          puts.push(JSON.parse(String(init?.body ?? "{}")));
          state = true;
          return ok({ configured: true });
        }
        return ok({ configured: state });
      }
      return ok({});
    }),
  );
  return puts;
}

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <AdzunaSettings />
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("AdzunaSettings (OPP-222)", () => {
  it("affiche l'état « non configurées » et le formulaire pour un reviewer", async () => {
    stubSettings("reviewer", false);
    renderSettings();

    expect(await screen.findByText("Non configurées")).toBeInTheDocument();
    expect(screen.getByLabelText("App ID Adzuna")).toBeInTheDocument();
    expect(screen.getByLabelText("App Key Adzuna")).toBeInTheDocument();
  });

  it("enregistre les clés (PUT app_id/app_key), vide les champs et passe à « configurées »", async () => {
    const puts = stubSettings("reviewer", false);
    renderSettings();
    await screen.findByLabelText("App ID Adzuna");

    await userEvent.type(screen.getByLabelText("App ID Adzuna"), "my-id");
    await userEvent.type(screen.getByLabelText("App Key Adzuna"), "my-key");
    await userEvent.click(screen.getByRole("button", { name: /Enregistrer les clés/ }));

    expect(await screen.findByText("Clés Adzuna enregistrées.")).toBeInTheDocument();
    expect(puts).toEqual([{ app_id: "my-id", app_key: "my-key" }]);
    // Les champs sont vidés : un secret ne reste pas dans le DOM après l'enregistrement.
    expect((screen.getByLabelText("App ID Adzuna") as HTMLInputElement).value).toBe("");
    // L'état relu (invalidation) reflète la configuration.
    expect(await screen.findByText("Configurées")).toBeInTheDocument();
  });

  it("n'expose pas de formulaire à un non-reviewer", async () => {
    stubSettings("viewer", false);
    renderSettings();

    expect(await screen.findByText(/Un reviewer peut renseigner/)).toBeInTheDocument();
    expect(screen.queryByLabelText("App ID Adzuna")).not.toBeInTheDocument();
  });
});
