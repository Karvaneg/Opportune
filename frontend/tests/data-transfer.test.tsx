import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";
import { DataTransferSettings } from "../src/components/DataTransferSettings";
import { importConfirmation } from "../src/components/ImportDataPicker";
import { saveZipFile } from "../src/lib/saveFile";
import { SpaceProvider } from "../src/space/SpaceContext";

// L'enregistrement du fichier (fenêtre « Enregistrer sous ») est remplacé : jsdom n'en a pas.
vi.mock("../src/lib/saveFile", () => ({ saveZipFile: vi.fn() }));

const respond = (status: number, body: unknown) =>
  Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);

const EXPORT_PATH = "/home/moi/Téléchargements/opportune-export-2026-11-05.zip";

/** fetch factice : mémorise les POST /data/* et rend la réponse d'import fournie. */
function stubApi(importResponse = { status: 200, body: { status: "imported" } as unknown }) {
  const posts: Array<{ path: string; body: Record<string, unknown> }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return respond(200, { id: "u", owned_count: 1, owned_candidate_ids: ["c"] });
      if (s.includes("/data/")) {
        posts.push({ path: s, body: JSON.parse(String(init?.body ?? "{}")) });
        if (s.includes("/data/export"))
          return respond(200, {
            archive_base64: btoa("contenu"),
            filename: "opportune-export-2026-11-05.zip",
          });
        return respond(importResponse.status, importResponse.body);
      }
      return respond(200, {});
    }),
  );
  return posts;
}

function renderSettings(space: "mine" | "demo") {
  sessionStorage.setItem("opportune.space", space);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <SpaceProvider>
      <ApiStatusProvider>
        <QueryClientProvider client={queryClient}>
          <DataTransferSettings />
        </QueryClientProvider>
      </ApiStatusProvider>
    </SpaceProvider>,
  );
}

const zipFile = () => new File(["contenu"], "opportune-export.zip", { type: "application/zip" });

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("DataTransferSettings (OPP-232)", () => {
  it("enregistre l'archive à l'endroit choisi et affiche ce chemin", async () => {
    const posts = stubApi();
    vi.mocked(saveZipFile).mockResolvedValue(EXPORT_PATH);
    renderSettings("mine");

    await userEvent.click(await screen.findByRole("button", { name: "Exporter mes données" }));

    expect(await screen.findByText(EXPORT_PATH)).toBeInTheDocument();
    expect(posts.map((post) => post.path)).toEqual(["/api/data/export"]);
    const [bytes, filename] = vi.mocked(saveZipFile).mock.calls[0];
    expect(new TextDecoder().decode(bytes)).toBe("contenu");
    expect(filename).toBe("opportune-export-2026-11-05.zip");
  });

  it("n'affiche rien si l'enregistrement est annulé", async () => {
    stubApi();
    vi.mocked(saveZipFile).mockResolvedValue(null);
    renderSettings("mine");

    await userEvent.click(await screen.findByRole("button", { name: "Exporter mes données" }));

    await vi.waitFor(() => expect(saveZipFile).toHaveBeenCalled());
    expect(screen.queryByText(/Données exportées/)).toBeNull();
  });

  it("importe après confirmation et envoie le fichier en base64", async () => {
    const posts = stubApi();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderSettings("mine");
    await screen.findByRole("button", { name: "Importer des données" });

    await userEvent.upload(screen.getByLabelText("Fichier d'export Opportune"), zipFile());

    expect(await screen.findByText("Données importées.")).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledWith(importConfirmation("mine"));
    expect(posts).toEqual([{ path: "/api/data/import", body: { archive_base64: btoa("contenu") } }]);
  });

  it("n'importe rien si la confirmation est refusée", async () => {
    const posts = stubApi();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderSettings("mine");
    await screen.findByRole("button", { name: "Importer des données" });

    await userEvent.upload(screen.getByLabelText("Fichier d'export Opportune"), zipFile());

    expect(posts).toEqual([]);
  });

  it("affiche l'erreur d'un import refusé", async () => {
    stubApi({ status: 400, body: { error: "ce fichier n'est pas un export d'Opportune" } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderSettings("mine");
    await screen.findByRole("button", { name: "Importer des données" });

    await userEvent.upload(screen.getByLabelText("Fichier d'export Opportune"), zipFile());

    expect(await screen.findByText(/pas un export d'Opportune/)).toBeInTheDocument();
  });

  it("apparaît aussi dans l'espace Démo, en nommant cet espace", async () => {
    stubApi();

    renderSettings("demo");

    expect(await screen.findByRole("button", { name: "Exporter mes données" })).toBeInTheDocument();
    expect(screen.getByText(/toutes les données de « Démo »/)).toBeInTheDocument();
  });
});
