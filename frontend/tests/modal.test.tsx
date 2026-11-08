import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Modal } from "../src/components/Modal";

/** Bouton qui ouvre une fenêtre à deux boutons, comme une confirmation. */
function ModalHarness() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Ouvrir
      </button>
      {open && (
        <Modal label="Confirmer" onClose={() => setOpen(false)}>
          <p>Texte à sélectionner</p>
          <button type="button">Annuler</button>
          <button type="button">Valider</button>
        </Modal>
      )}
    </>
  );
}

async function openModal() {
  render(<ModalHarness />);
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));
  return screen.getByRole("dialog", { name: "Confirmer" });
}

describe("Modal (OPP-246)", () => {
  it("donne le focus au premier bouton de la fenêtre à l'ouverture", async () => {
    await openModal();

    const focusedButton = screen.getByRole("button", { name: "Annuler" });

    expect(focusedButton).toHaveFocus();
  });

  it("Tab après le dernier bouton revient au premier, sans sortir de la fenêtre", async () => {
    await openModal();
    screen.getByRole("button", { name: "Valider" }).focus();

    await userEvent.tab();

    expect(screen.getByRole("button", { name: "Annuler" })).toHaveFocus();
  });

  it("Maj+Tab depuis le premier bouton va au dernier", async () => {
    await openModal();

    await userEvent.tab({ shift: true });

    expect(screen.getByRole("button", { name: "Valider" })).toHaveFocus();
  });

  it("une sélection commencée dans la fenêtre et relâchée sur le fond ne ferme pas", async () => {
    const modalDialog = await openModal();
    const backdrop = modalDialog.parentElement!;

    fireEvent.mouseDown(screen.getByText("Texte à sélectionner"));
    fireEvent.click(backdrop);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("un clic entièrement sur le fond ferme et rend le focus au bouton d'ouverture", async () => {
    const modalDialog = await openModal();
    const backdrop = modalDialog.parentElement!;

    fireEvent.mouseDown(backdrop);
    fireEvent.click(backdrop);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ouvrir" })).toHaveFocus();
  });

  it("Échap ferme la fenêtre", async () => {
    await openModal();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
