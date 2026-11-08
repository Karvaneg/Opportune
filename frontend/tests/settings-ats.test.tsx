import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AtsSettings } from "../src/components/AtsSettings";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";

const respond = (status: number, body: unknown) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);

type Company = { url: string; ats: string; slug: string; offers_in_france: number | null };

/** fetch factice **stateful** : le PUT /settings/ats rend la réponse fournie et la mémorise
 * pour le GET suivant, comme le vrai back. */
function stubSettings(
  companies: Company[] = [],
  putResponse?: { status: number; body: unknown },
) {
  const puts: Array<Record<string, unknown>> = [];
  let state = companies;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return respond(200, { id: "u", owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/settings/ats")) {
        if (init?.method === "PUT") {
          puts.push(JSON.parse(String(init?.body ?? "{}")));
          const response = putResponse ?? { status: 200, body: { companies: [] } };
          if (response.status === 200) state = (response.body as { companies: Company[] }).companies;
          return respond(response.status, response.body);
        }
        return respond(200, { companies: state });
      }
      return respond(200, {});
    }),
  );
  return puts;
}

function renderSettings() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ApiStatusProvider>
      <QueryClientProvider client={queryClient}>
        <AtsSettings />
      </QueryClientProvider>
    </ApiStatusProvider>,
  );
}

const SWILE: Company = { url: "https://jobs.lever.co/swile", ats: "lever", slug: "swile", offers_in_france: null };

afterEach(() => vi.unstubAllGlobals());

describe("AtsSettings (OPP-226)", () => {
  it("affiche « Aucune entreprise » et le champ", async () => {
    stubSettings([]);

    renderSettings();

    expect(await screen.findByText("Aucune entreprise")).toBeInTheDocument();
    expect(screen.getByLabelText("Pages carrière des entreprises ciblées")).toBeInTheDocument();
  });

  it("préremplit le champ avec les pages carrière enregistrées", async () => {
    stubSettings([SWILE]);

    renderSettings();

    const field = (await screen.findByLabelText("Pages carrière des entreprises ciblées")) as HTMLTextAreaElement;
    expect(field.value).toBe("https://jobs.lever.co/swile");
    expect(screen.getByText("1 entreprise")).toBeInTheDocument();
  });

  it("enregistre, resynchronise le champ et affiche les offres en France des entreprises vérifiées", async () => {
    const puts = stubSettings([], {
      status: 200,
      body: { companies: [{ ...SWILE, offers_in_france: 17 }] },
    });
    renderSettings();
    const field = (await screen.findByLabelText("Pages carrière des entreprises ciblées")) as HTMLTextAreaElement;

    await userEvent.type(field, "jobs.lever.co/swile/");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer les entreprises" }));

    expect(await screen.findByText("Entreprises ciblées enregistrées.")).toBeInTheDocument();
    expect(screen.getByText(/17 offres en France actuellement/)).toBeInTheDocument();
    expect(puts).toEqual([{ companies: ["jobs.lever.co/swile/"] }]);
    expect((screen.getByLabelText("Pages carrière des entreprises ciblées") as HTMLTextAreaElement).value).toBe(
      "https://jobs.lever.co/swile",
    );
  });

  it("affiche le refus du back (URL non reconnue) sans rien enregistrer", async () => {
    stubSettings([], {
      status: 400,
      body: { error: "URL non reconnue : https://wttj.com/x" },
    });
    renderSettings();
    const field = await screen.findByLabelText("Pages carrière des entreprises ciblées");

    await userEvent.type(field, "https://wttj.com/x");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer les entreprises" }));

    expect(await screen.findByText(/URL non reconnue/)).toBeInTheDocument();
    expect(screen.getByText("Aucune entreprise")).toBeInTheDocument();
  });

  it("supprime toutes les entreprises après confirmation quand on vide le champ", async () => {
    const puts = stubSettings([SWILE]);
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderSettings();
    const field = await screen.findByLabelText("Pages carrière des entreprises ciblées");

    await userEvent.clear(field);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer toutes les entreprises" }));

    expect(await screen.findByText("Entreprises ciblées supprimées.")).toBeInTheDocument();
    expect(puts).toEqual([{ companies: [] }]);
  });

  it("n'envoie rien si on annule la confirmation de suppression", async () => {
    const puts = stubSettings([SWILE]);
    vi.stubGlobal("confirm", vi.fn(() => false));
    renderSettings();
    const field = await screen.findByLabelText("Pages carrière des entreprises ciblées");

    await userEvent.clear(field);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer toutes les entreprises" }));

    expect(puts).toEqual([]);
  });

});
