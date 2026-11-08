import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RssSettings } from "../src/components/RssSettings";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/** fetch factice **stateful** : le PUT /settings/rss nettoie la liste (ne garde que les URLs
 * http(s)) et la mémorise pour le GET suivant — comme le vrai back, pour vérifier le refetch et
 * la resynchronisation du champ après enregistrement. */
function stubSettings(feeds: string[] = []) {
  const puts: Array<Record<string, unknown>> = [];
  let state = feeds;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/settings/rss")) {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init?.body ?? "{}"));
          puts.push(body);
          const cleaned = (body.feeds as string[]).filter((u) => /^https?:\/\//.test(u));
          state = cleaned;
          return ok({ feeds: cleaned });
        }
        return ok({ feeds: state });
      }
      return ok({});
    }),
  );
  return puts;
}

function renderSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ApiStatusProvider>
      <QueryClientProvider client={qc}>
        <RssSettings />
      </QueryClientProvider>
    </ApiStatusProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RssSettings (OPP-195)", () => {
  it("affiche « Aucun flux » et le champ", async () => {
    stubSettings([]);
    renderSettings();

    expect(await screen.findByText("Aucun flux")).toBeInTheDocument();
    expect(screen.getByLabelText("URLs des flux RSS")).toBeInTheDocument();
  });

  it("préremplit le champ avec les flux enregistrés", async () => {
    stubSettings(["https://a.example/f", "https://b.example/f"]);
    renderSettings();

    const field = (await screen.findByLabelText("URLs des flux RSS")) as HTMLTextAreaElement;
    expect(field.value).toBe("https://a.example/f\nhttps://b.example/f");
    expect(screen.getByText("2 flux configurés")).toBeInTheDocument();
  });

  it("enregistre les flux (PUT feeds) et resynchronise le champ sur la liste nettoyée", async () => {
    const puts = stubSettings([]);
    renderSettings();
    const field = (await screen.findByLabelText("URLs des flux RSS")) as HTMLTextAreaElement;

    // Une URL valide + une ligne sans schéma : le back rejette la seconde, le champ doit s'aligner.
    await userEvent.type(field, "https://ok.example/f\npas-une-url");
    await userEvent.click(screen.getByRole("button", { name: /Enregistrer les flux/ }));

    expect(await screen.findByText("Flux RSS enregistrés.")).toBeInTheDocument();
    expect(puts).toEqual([{ feeds: ["https://ok.example/f", "pas-une-url"] }]);
    expect((screen.getByLabelText("URLs des flux RSS") as HTMLTextAreaElement).value).toBe(
      "https://ok.example/f",
    );
  });

  it("supprime tous les flux quand on vide le champ et confirme (PUT feeds vide)", async () => {
    const puts = stubSettings(["https://a.example/f"]);
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderSettings();
    const field = (await screen.findByLabelText("URLs des flux RSS")) as HTMLTextAreaElement;

    await userEvent.clear(field);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer tous les flux" }));

    expect(await screen.findByText("Flux RSS supprimés.")).toBeInTheDocument();
    expect(puts).toEqual([{ feeds: [] }]);
    expect(await screen.findByText("Aucun flux")).toBeInTheDocument();
  });

  it("n'envoie rien si l'utilisateur annule la confirmation de suppression", async () => {
    const puts = stubSettings(["https://a.example/f"]);
    vi.stubGlobal("confirm", vi.fn(() => false));
    renderSettings();
    const field = (await screen.findByLabelText("URLs des flux RSS")) as HTMLTextAreaElement;

    await userEvent.clear(field);
    await userEvent.click(screen.getByRole("button", { name: "Supprimer tous les flux" }));

    expect(puts).toEqual([]);
    expect(screen.getByText("1 flux configuré")).toBeInTheDocument();
  });

  it("efface le message de succès dès qu'on modifie le champ", async () => {
    stubSettings([]);
    renderSettings();
    const field = (await screen.findByLabelText("URLs des flux RSS")) as HTMLTextAreaElement;
    await userEvent.type(field, "https://ok.example/f");
    await userEvent.click(screen.getByRole("button", { name: /Enregistrer les flux/ }));
    await screen.findByText("Flux RSS enregistrés.");

    await userEvent.type(field, "\nhttps://autre.example/f");

    expect(screen.queryByText("Flux RSS enregistrés.")).not.toBeInTheDocument();
  });

  it("garde le bouton inactif sur champ vide quand aucun flux n'est enregistré", async () => {
    stubSettings([]);
    renderSettings();

    await screen.findByLabelText("URLs des flux RSS");

    expect(screen.getByRole("button", { name: /Enregistrer les flux/ })).toBeDisabled();
  });

});
