import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";
import type { UninstallInfo } from "../src/api/system";
import { UninstallSettings } from "../src/components/UninstallSettings";
import { formatBytes } from "../src/lib/formatBytes";

const GIGABYTE = 1024 ** 3;

const json = (status: number, body: unknown) =>
  Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);

function uninstallInfo(overrides: Partial<UninstallInfo> = {}): UninstallInfo {
  return {
    available: true,
    install_kind: "deb",
    appimage_path: null,
    data_dir: "/home/marie/.local/share/com.opportune.app",
    model: { name: "ministral-3:3b", present: true, removable: true, app_copy_bytes: 3 * GIGABYTE },
    user_has_own_ollama: false,
    ...overrides,
  };
}

/** fetch factice : GET /system/uninstall rend `info` ; les POST sont notés puis acceptés
 * (ou refusés avec `postStatus`). */
function stubUninstall(info: UninstallInfo | null, postStatus = 202) {
  const posts: Array<Record<string, unknown>> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (String(url).includes("/system/uninstall")) {
        if (init?.method === "POST") {
          posts.push(JSON.parse(String(init?.body ?? "{}")));
          return postStatus === 202
            ? json(202, { accepted: true })
            : json(postStatus, { error: "le modèle n'a pas pu être supprimé d'Ollama" });
        }
        return info ? json(200, info) : json(404, { error: "désinstallation non disponible" });
      }
      return json(200, {});
    }),
  );
  return posts;
}

function renderSettings() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ApiStatusProvider>
      <QueryClientProvider client={queryClient}>
        <UninstallSettings />
      </QueryClientProvider>
    </ApiStatusProvider>,
  );
}

async function openDialog() {
  await userEvent.click(await screen.findByRole("button", { name: "Désinstaller Opportune…" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("UninstallSettings (OPP-252)", () => {
  it("n'affiche rien hors app de bureau", async () => {
    stubUninstall(uninstallInfo({ available: false, install_kind: null }));

    const { container } = renderSettings();

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("n'affiche rien quand le back ne connaît pas la route", async () => {
    stubUninstall(null);

    const { container } = renderSettings();

    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("coche le modèle par défaut, pas les données", async () => {
    stubUninstall(uninstallInfo());
    renderSettings();

    await openDialog();

    expect(screen.getByRole("checkbox", { name: /Le modèle d'IA téléchargé par Opportune/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Mes données Opportune/ })).not.toBeChecked();
    expect(screen.getByText(/3 Go/)).toBeInTheDocument();
  });

  it("envoie les choix cochés puis annonce la fermeture", async () => {
    const posts = stubUninstall(uninstallInfo());
    renderSettings();
    await openDialog();

    await userEvent.click(screen.getByRole("checkbox", { name: /Mes données Opportune/ }));
    await userEvent.click(screen.getByRole("button", { name: "Désinstaller et fermer Opportune" }));

    expect(await screen.findByText("Opportune va se fermer dans un instant.")).toBeInTheDocument();
    expect(posts).toEqual([{ remove_model: true, remove_data: true }]);
  });

  /** Ouvre la fenêtre, confirme, puis laisse passer le délai sans que l'app se ferme. */
  async function confirmThenWaitForTimeout() {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    stubUninstall(uninstallInfo());
    renderSettings();
    await user.click(await screen.findByRole("button", { name: "Désinstaller Opportune…" }));
    await user.click(screen.getByRole("button", { name: "Désinstaller et fermer Opportune" }));
    await screen.findByText("Opportune va se fermer dans un instant.");
    await act(() => vi.advanceTimersByTimeAsync(20_000));
    return user;
  }

  it("signale que l'app ne s'est pas fermée au bout du délai", async () => {
    await confirmThenWaitForTimeout();

    expect(screen.getByText("Opportune ne s'est pas fermée")).toBeInTheDocument();
    expect(screen.getByText("/home/marie/.local/share/com.opportune.app")).toBeInTheDocument();
  });

  it("laisse fermer la fenêtre après le délai", async () => {
    const user = await confirmThenWaitForTimeout();

    await user.click(screen.getByRole("button", { name: "Fermer" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("n'envoie rien quand on annule", async () => {
    const posts = stubUninstall(uninstallInfo());
    renderSettings();
    await openDialog();

    await userEvent.click(screen.getByRole("button", { name: "Annuler" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(posts).toEqual([]);
  });

  it("ne propose pas de supprimer un modèle qui était déjà là", async () => {
    stubUninstall(
      uninstallInfo({
        model: { name: "ministral-3:3b", present: true, removable: false, app_copy_bytes: 0 },
      }),
    );
    renderSettings();

    await openDialog();

    expect(screen.queryByRole("checkbox", { name: /Le modèle d'IA/ })).not.toBeInTheDocument();
    expect(screen.getByText(/était déjà sur ton ordinateur avant/)).toBeInTheDocument();
  });

  it("ne demande jamais la suppression d'un modèle qui était déjà là", async () => {
    const posts = stubUninstall(
      uninstallInfo({
        model: { name: "ministral-3:3b", present: true, removable: false, app_copy_bytes: 0 },
      }),
    );
    renderSettings();
    await openDialog();

    await userEvent.click(screen.getByRole("button", { name: "Désinstaller et fermer Opportune" }));

    await screen.findByText("Opportune va se fermer dans un instant.");
    expect(posts).toEqual([{ remove_model: false, remove_data: false }]);
  });

  it("indique où restent les données non supprimées", async () => {
    stubUninstall(uninstallInfo());
    renderSettings();

    await openDialog();

    expect(screen.getByText("/home/marie/.local/share/com.opportune.app")).toBeInTheDocument();
  });

  it("avertit que la suppression des données est définitive", async () => {
    stubUninstall(uninstallInfo());
    renderSettings();
    await openDialog();

    await userEvent.click(screen.getByRole("checkbox", { name: /Mes données Opportune/ }));

    expect(screen.getByText(/Cette suppression est définitive/)).toBeInTheDocument();
  });

  it.each([
    ["deb", "sudo apt remove opportune"],
    ["rpm", "sudo rpm -e opportune"],
  ] as const)("donne la commande à lancer pour un paquet %s", async (kind, command) => {
    stubUninstall(uninstallInfo({ install_kind: kind }));
    renderSettings();

    await openDialog();

    expect(screen.getByText(command)).toBeInTheDocument();
  });

  it("donne le fichier à supprimer pour une AppImage", async () => {
    stubUninstall(
      uninstallInfo({ install_kind: "appimage", appimage_path: "/home/marie/Opportune.AppImage" }),
    );
    renderSettings();

    await openDialog();

    expect(screen.getByText("/home/marie/Opportune.AppImage")).toBeInTheDocument();
  });

  it.each([
    ["windows-nsis", /le désinstalleur s'ouvre/],
    ["windows-msi", /« Applications installées » de Windows s'ouvre/],
    ["linux-other", /gestionnaire de paquets de ta distribution/],
    ["macos", /vers la\s+corbeille/],
    ["dev", /lancée depuis le code source/],
  ] as const)("explique la suite pour une installation %s", async (kind, expectedText) => {
    stubUninstall(uninstallInfo({ install_kind: kind }));
    renderSettings();

    await openDialog();

    expect(screen.getByText(expectedText)).toBeInTheDocument();
  });

  it("signale l'Ollama personnel et dit qu'il n'est pas touché", async () => {
    stubUninstall(uninstallInfo({ user_has_own_ollama: true }));
    renderSettings();

    await openDialog();

    expect(screen.getByText(/Opportune n'y touche pas/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /la documentation d'Ollama/ })).toBeInTheDocument();
  });

  it("ne parle pas d'Ollama personnel quand il n'y en a pas", async () => {
    stubUninstall(uninstallInfo({ user_has_own_ollama: false }));
    renderSettings();

    await openDialog();

    expect(screen.queryByText(/ton propre Ollama/)).not.toBeInTheDocument();
  });

  it("affiche l'erreur et garde la fenêtre ouverte si la demande échoue", async () => {
    stubUninstall(uninstallInfo(), 502);
    renderSettings();
    await openDialog();

    await userEvent.click(screen.getByRole("button", { name: "Désinstaller et fermer Opportune" }));

    expect(await screen.findByRole("button", { name: "Désinstaller et fermer Opportune" })).toBeEnabled();
    expect(screen.queryByText("Opportune va se fermer dans un instant.")).not.toBeInTheDocument();
    expect(await screen.findByText(/n'a pas pu être supprimé/)).toBeInTheDocument();
  });
});

describe("formatBytes", () => {
  it.each([
    [3 * GIGABYTE, "3 Go"],
    [2.84 * GIGABYTE, "2,8 Go"],
    [512 * 1024 ** 2, "512 Mo"],
    [10, "1 Mo"],
  ])("formate %d octets en « %s »", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });
});
