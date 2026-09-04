import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "../src/components/StatusBadge";

describe("StatusBadge", () => {
  it("rend le libellé FR d'un statut de pré-évaluation", () => {
    render(<StatusBadge kind="advisory" value="approved" />);
    expect(screen.getByText("Pré-approuvé")).toBeInTheDocument();
  });

  it("rend le libellé FR d'un statut de décision humaine", () => {
    render(<StatusBadge kind="decision" value="deferred" />);
    expect(screen.getByText("Reporté")).toBeInTheDocument();
  });
});
