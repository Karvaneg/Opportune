import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  attentionClass,
  requestSettingsAttention,
  useSettingsAttention,
} from "../src/lib/settingsAttention";

function AttentionProbe() {
  const attention = useSettingsAttention();
  return <span key={attention} data-testid="probe" className={attentionClass(attention)} />;
}

describe("settingsAttention (OPP-227)", () => {
  it("n'anime rien tant qu'aucune demande n'a été faite", () => {
    render(<AttentionProbe />);

    const probe = screen.getByTestId("probe");

    expect(probe).not.toHaveClass("motion-safe:animate-attention");
  });

  it("anime les abonnés et remonte l'élément à chaque nouvelle demande", () => {
    render(<AttentionProbe />);
    act(() => requestSettingsAttention());
    const probeAfterFirstRequest = screen.getByTestId("probe");

    act(() => requestSettingsAttention());
    const probeAfterSecondRequest = screen.getByTestId("probe");

    expect(probeAfterSecondRequest).toHaveClass("motion-safe:animate-attention");
    expect(probeAfterSecondRequest).not.toBe(probeAfterFirstRequest);
  });
});
