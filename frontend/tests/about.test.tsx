import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import packageJson from "../package.json";
import { AboutButton } from "../src/components/AboutDialog";
import { WelcomeScreen } from "../src/space/WelcomeScreen";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openAbout() {
  render(<AboutButton />);
  await userEvent.click(screen.getByRole("button", { name: "À propos d'Opportune" }));
  return screen.getByRole("dialog", { name: "À propos d'Opportune" });
}

describe("À propos (OPP-246)", () => {
  it("affiche la version de package.json, la licence, l'autrice et le dépôt", async () => {
    const expectedVersion = `v${packageJson.version}`;

    const aboutDialog = await openAbout();

    expect(aboutDialog).toHaveTextContent(expectedVersion);
    // Noms exacts : la flèche « ↗ » est masquée au lecteur d'écran.
    expect(screen.getByRole("link", { name: "MIT" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Marie Le Carvennec" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "github.com/Karvaneg/Opportune" })).toBeInTheDocument();
  });

  it("ouvre le dépôt dans le navigateur, sans quitter l'app", async () => {
    const windowOpen = vi.fn();
    vi.stubGlobal("open", windowOpen);
    await openAbout();

    await userEvent.click(screen.getByRole("link", { name: /github\.com\/Karvaneg\/Opportune/ }));

    expect(windowOpen).toHaveBeenCalledWith(
      "https://github.com/Karvaneg/Opportune",
      "_blank",
      "noopener,noreferrer",
    );
  });

  it("se ferme avec Échap et rend le focus au bouton « ? »", async () => {
    await openAbout();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "À propos d'Opportune" })).toHaveFocus();
  });

  it("se ferme avec le bouton Fermer", async () => {
    await openAbout();

    await userEvent.click(screen.getByRole("button", { name: "Fermer" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("se ferme avec un clic à côté de la fenêtre", async () => {
    const aboutDialog = await openAbout();
    const backdrop = aboutDialog.parentElement!;

    await userEvent.click(backdrop);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("reste ouverte quand on clique dans la fenêtre", async () => {
    const aboutDialog = await openAbout();

    await userEvent.click(aboutDialog);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});

describe("Écran d'accueil, pied de page (OPP-246)", () => {
  it("affiche le nom, la version, l'année et l'autrice", () => {
    const expectedFooter = `Opportune v${packageJson.version} · © 2026 Marie Le Carvennec`;

    render(<WelcomeScreen onChoose={vi.fn()} />);

    expect(screen.getByRole("contentinfo")).toHaveTextContent(expectedFooter);
  });
});
