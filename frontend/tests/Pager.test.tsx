import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Pager } from "../src/components/Pager";

describe("Pager", () => {
  it("désactive « Précédent » sur la première page", () => {
    render(<Pager page={1} totalPages={3} total={42} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
  });

  it("désactive « Suivant » sur la dernière page", () => {
    render(<Pager page={3} totalPages={3} total={42} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Précédent" })).toBeEnabled();
  });

  it("désactive les deux boutons quand busy", () => {
    render(<Pager page={2} totalPages={3} total={42} onPrev={vi.fn()} onNext={vi.fn()} busy />);
    expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });

  it("affiche au moins 1 page même quand totalPages vaut 0", () => {
    render(<Pager page={1} totalPages={0} total={0} onPrev={vi.fn()} onNext={vi.fn()} />);
    expect(screen.getByText(/Page 1 \/ 1/)).toBeInTheDocument();
  });

  it("déclenche onPrev / onNext au clic", async () => {
    const onPrev = vi.fn();
    const onNext = vi.fn();
    render(<Pager page={2} totalPages={3} total={42} onPrev={onPrev} onNext={onNext} />);

    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    await userEvent.click(screen.getByRole("button", { name: "Précédent" }));

    expect(onNext).toHaveBeenCalledOnce();
    expect(onPrev).toHaveBeenCalledOnce();
  });
});
