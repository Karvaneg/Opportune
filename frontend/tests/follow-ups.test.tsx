import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { followUpOrigin, followUpRank, type FollowUpStep } from "../src/api/followUps";
import { ApiStatusProvider } from "../src/api/ApiStatusContext";
import { FollowUpSettings, parseDays } from "../src/components/FollowUpSettings";

const FOLLOW_UP: FollowUpStep = {
  since: "candidature",
  start_date: "2026-11-01",
  due_date: "2026-11-06",
  step: 1,
  total: 2,
};

const ok = (body: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);

/** fetch factice : `/me`, puis la réponse donnée pour tout le reste. */
function stubFetch(body: unknown) {
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
    if (String(url).includes("/me"))
      return ok({ id: "u", owned_count: 1, owned_candidate_ids: ["cand-1"] });
    return ok(body);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ApiStatusProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ApiStatusProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("followUpRank / followUpOrigin", () => {
  it("décrit la 1re relance après une candidature", () => {
    const afterApplication = FOLLOW_UP;

    const label = `${followUpRank(afterApplication)} · ${followUpOrigin(afterApplication)}`;

    expect(label).toBe("1re relance sur 2 · après la candidature du 01/11/2026");
  });

  it("décrit la 3e relance après un entretien", () => {
    const afterInterview: FollowUpStep = {
      ...FOLLOW_UP, since: "entretien", start_date: "2026-11-12", step: 3, total: 3,
    };

    const label = `${followUpRank(afterInterview)} · ${followUpOrigin(afterInterview)}`;

    expect(label).toBe("3e relance sur 3 · après l'entretien du 12/11/2026");
  });
});

describe("parseDays", () => {
  it("lit des jours séparés par des virgules", () => {
    const text = " 5, 8 ,15 ";

    const days = parseDays(text);

    expect(days).toEqual([5, 8, 15]);
  });

  it("rend une liste vide pour un champ vide", () => {
    const emptyText = "  ";

    const days = parseDays(emptyText);

    expect(days).toEqual([]);
  });

  it("refuse un élément qui n'est pas un entier", () => {
    const textWithDecimal = "5, 8.5";

    const days = parseDays(textWithDecimal);

    expect(days).toBeNull();
  });
});

describe("FollowUpSettings", () => {
  it("affiche les délais enregistrés et envoie les nouveaux", async () => {
    const fetchMock = stubFetch({ after_application: [5, 8], after_interview: [5, 8, 15] });
    renderWithProviders(<FollowUpSettings />);
    const applicationField = await screen.findByLabelText("Après une candidature (jours)");

    await userEvent.clear(applicationField);
    await userEvent.type(applicationField, "3, 7");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer les délais" }));

    expect(screen.getByLabelText("Après un entretien (jours)")).toHaveValue("5, 8, 15");
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
      expect(JSON.parse(String(put?.[1]?.body))).toEqual({
        after_application: [3, 7],
        after_interview: [5, 8, 15],
      });
    });
  });

  it("désactive l'enregistrement si la saisie n'est pas valide", async () => {
    stubFetch({ after_application: [5, 8], after_interview: [5, 8, 15] });
    renderWithProviders(<FollowUpSettings />);
    const interviewField = await screen.findByLabelText("Après un entretien (jours)");

    await userEvent.type(interviewField, ", abc");

    expect(screen.getByRole("button", { name: "Enregistrer les délais" })).toBeDisabled();
    expect(screen.getByText(/nombres entiers de jours/)).toBeInTheDocument();
  });
});
