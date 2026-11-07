import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ScoringQuality } from "../src/api/types";
import { ScoringQualityCard, verdictText } from "../src/components/ScoringQualityCard";

function group(count: number, mean: number | null, high = 0, medium = 0, low = 0) {
  return { count, mean, bands: { high, medium, low } };
}

function quality(overrides: Partial<ScoringQuality>): ScoringQuality {
  return {
    retained: group(0, null),
    rejected: group(0, null),
    min_per_group: 10,
    verdict: "insuffisant",
    gap: null,
    high_threshold: 80,
    medium_threshold: 60,
    ...overrides,
  };
}

function renderCard(body: ScoringQuality) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response),
    ),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ScoringQualityCard candidateId="cand-1" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("verdictText", () => {
  it("explique ce qui manque quand les décisions sont insuffisantes", () => {
    const fewDecisions = quality({ retained: group(3, 80), rejected: group(12, 50) });

    const text = verdictText(fewDecisions);

    expect(text).toContain("au moins 10 offres retenues et 10 rejetées");
    expect(text).toContain("3 retenue(s) et 12 rejetée(s)");
  });

  it("donne l'écart quand les offres retenues ont un meilleur score", () => {
    const retainedHigher = quality({
      retained: group(10, 78.5),
      rejected: group(10, 61),
      verdict: "retenues_mieux_notees",
      gap: 17.5,
    });

    const text = verdictText(retainedHigher);

    expect(text).toContain("+17,5 points");
    expect(text).toContain("le score t'aide à trier");
  });

  it("affiche l'écart calculé par l'API, pas celui des moyennes arrondies", () => {
    const roundedMeansDiffer = quality({
      retained: group(10, 70.1),
      rejected: group(10, 70),
      verdict: "retenues_mieux_notees",
      gap: 0.2,
    });

    const text = verdictText(roundedMeansDiffer);

    expect(text).toContain("+0,2 points");
  });

  it("ne dit pas « +0 points » quand l'écart réel est sous 0,1 point", () => {
    const tinyGap = quality({
      retained: group(10, 70),
      rejected: group(10, 70),
      verdict: "retenues_mieux_notees",
      gap: 0,
    });

    const text = verdictText(tinyGap);

    expect(text).toContain("écart inférieur à 0,1 point");
    expect(text).not.toContain("+0 points");
  });

  it("dit que le score n'aide pas quand les retenues ne sont pas mieux notées", () => {
    const retainedNotHigher = quality({
      retained: group(10, 60),
      rejected: group(10, 65),
      verdict: "retenues_pas_mieux_notees",
    });

    const text = verdictText(retainedNotHigher);

    expect(text).toContain("le score ne t'aide pas encore à trier");
  });
});

describe("ScoringQualityCard", () => {
  it("affiche la moyenne et les tranches de chaque groupe", async () => {
    const decided = quality({
      retained: group(10, 78.5, 6, 3, 1),
      rejected: group(11, 61, 1, 4, 6),
      verdict: "retenues_mieux_notees",
    });

    renderCard(decided);

    expect(await screen.findByText("Retenues (10)")).toBeInTheDocument();
    expect(screen.getByText("Rejetées (11)")).toBeInTheDocument();
    expect(screen.getByText("78,5")).toBeInTheDocument();
    expect(screen.getByText("80 et plus")).toBeInTheDocument();
    expect(screen.getByText("60 à 79")).toBeInTheDocument();
    expect(screen.getByText("Moins de 60")).toBeInTheDocument();
  });

  it("n'affiche rien sans aucune décision", async () => {
    const noDecision = quality({});

    renderCard(noDecision);

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByText("Qualité du score")).not.toBeInTheDocument();
  });

  it("n'affiche pas de bandeau d'erreur si l'API échoue", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ error: "introuvable" }),
        } as Response),
      ),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={qc}>
        <ScoringQualityCard candidateId="cand-1" />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText("Qualité du score")).not.toBeInTheDocument();
  });

  it("affiche l'état « pas encore assez » dès qu'une décision existe", async () => {
    const fewDecisions = quality({ retained: group(1, 80, 1, 0, 0) });

    renderCard(fewDecisions);

    expect(await screen.findByText(/Pas encore assez de décisions/)).toBeInTheDocument();
  });
});
