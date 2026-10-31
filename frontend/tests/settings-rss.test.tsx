import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RssSettings } from "../src/components/RssSettings";
import { AuthProvider } from "../src/auth/AuthContext";

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/** fetch factice **stateful** : le PUT /settings/rss nettoie la liste (ne garde que les URLs
 * http(s)) et la mémorise pour le GET suivant — comme le vrai back, pour vérifier le refetch et
 * la resynchronisation du champ après enregistrement. */
function stubSettings(role = "reviewer", feeds: string[] = []) {
  const puts: Array<Record<string, unknown>> = [];
  let state = feeds;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
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
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <RssSettings />
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RssSettings (OPP-195)", () => {
  it("affiche « Aucun flux » et le champ pour un reviewer", async () => {
    stubSettings("reviewer", []);
    renderSettings();

    expect(await screen.findByText("Aucun flux")).toBeInTheDocument();
    expect(screen.getByLabelText("URLs des flux RSS")).toBeInTheDocument();
  });

  it("préremplit le champ avec les flux enregistrés", async () => {
    stubSettings("reviewer", ["https://a.example/f", "https://b.example/f"]);
    renderSettings();

    const field = (await screen.findByLabelText("URLs des flux RSS")) as HTMLTextAreaElement;
    expect(field.value).toBe("https://a.example/f\nhttps://b.example/f");
    expect(screen.getByText("2 flux configurés")).toBeInTheDocument();
  });

  it("enregistre les flux (PUT feeds) et resynchronise le champ sur la liste nettoyée", async () => {
    const puts = stubSettings("reviewer", []);
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

  it("n'expose pas de champ à un non-reviewer", async () => {
    stubSettings("viewer", []);
    renderSettings();

    expect(await screen.findByText(/Un reviewer peut renseigner/)).toBeInTheDocument();
    expect(screen.queryByLabelText("URLs des flux RSS")).not.toBeInTheDocument();
  });
});
