import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProfilePanel } from "../src/components/ProfilePanel";
import { AuthProvider } from "../src/auth/AuthContext";

const PROFILE = {
  id: "cand-1", name: "Marie", skills: ["React", "Node.js"], contract_type: "CDI",
  location: null, languages: [], total_experience_years: null, experiences: [],
};

const EXPERIENCE = {
  title: "Développeuse Fullstack",
  company: "CBNSA",
  period: "2023 – 2025",
  location: "Gironde",
  highlights: ["Refonte d'un portail Symfony", "+45 % de trafic organique"],
  skills: ["Symfony", "PostgreSQL"],
};

const ok = (b: unknown) =>
  Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(b) } as Response);

/** fetch factice renvoyant un profil **figé** (lecture seule), paramétrable — pour les cas
 * d'affichage (parcours, état vide) qui n'exercent ni édition ni upload. */
function stubProfile(profile: Record<string, unknown>, role = "reviewer") {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      return ok(profile);
    }),
  );
}

/** fetch factice **stateful** : le PUT /profile persiste les skills que le GET renverra ensuite
 * (comme le vrai back, pour que le refetch post-édition reflète la mise à jour). */
function stubFetch(role = "reviewer") {
  const puts: Array<{ skills: string[] }> = [];
  let current = { ...PROFILE };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/profile")) {
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init?.body ?? "{}"));
          puts.push(body);
          current = { ...current, skills: body.skills };
          return ok(current);
        }
        return ok(current);
      }
      return ok(current);
    }),
  );
  return puts;
}

/** Variante du stub gérant aussi l'import de CV (`POST /profile/cv`) : enregistre les corps
 * postés et simule un profil reconstitué par l'analyse du CV. */
function stubFetchWithCv(role = "reviewer") {
  const posts: Array<Record<string, unknown>> = [];
  let current = { ...PROFILE };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const s = String(url);
      if (s.includes("/me"))
        return ok({ id: "u", role, owned_count: 1, owned_candidate_ids: ["cand-1"] });
      if (s.includes("/profile/cv")) {
        posts.push(JSON.parse(String(init?.body ?? "{}")));
        current = { ...current, name: "Marie (depuis CV)", skills: ["Python", "SQL"] };
        return ok(current);
      }
      if (s.includes("/profile")) return ok(current);
      return ok(current);
    }),
  );
  return posts;
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <AuthProvider>
      <QueryClientProvider client={qc}>
        <ProfilePanel candidateId="cand-1" />
      </QueryClientProvider>
    </AuthProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("ProfilePanel (OPP-158)", () => {
  it("affiche les compétences du profil", async () => {
    stubFetch();
    renderPanel();
    expect(await screen.findByText("React")).toBeInTheDocument();
    expect(screen.getByText("Node.js")).toBeInTheDocument();
  });

  it("ajoute une compétence et l'enregistre (PUT avec la liste complète)", async () => {
    const puts = stubFetch("reviewer");
    renderPanel();
    await screen.findByText("React");

    await userEvent.type(screen.getByLabelText("Ajouter une compétence"), "Agile");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Enregistrer les compétences/ }),
    );

    expect(await screen.findByText("Compétences à jour.")).toBeInTheDocument();
    expect(puts).toHaveLength(1);
    expect(puts[0].skills).toEqual(["React", "Node.js", "Agile"]);
  });

  it("retire une compétence avant d'enregistrer", async () => {
    const puts = stubFetch("reviewer");
    renderPanel();
    await screen.findByText("React");

    await userEvent.click(screen.getByRole("button", { name: "Retirer Node.js" }));
    await userEvent.click(
      screen.getByRole("button", { name: /Enregistrer les compétences/ }),
    );

    await screen.findByText("Compétences à jour.");
    expect(puts[0].skills).toEqual(["React"]);
  });

  it("n'ajoute pas un doublon (insensible à la casse)", async () => {
    stubFetch("reviewer");
    renderPanel();
    await screen.findByText("React");

    await userEvent.type(screen.getByLabelText("Ajouter une compétence"), "react");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter" }));

    // Toujours une seule puce « React » (le doublon « react » est ignoré).
    const list = screen.getByRole("list");
    expect(within(list).getAllByText(/^React$/i)).toHaveLength(1);
    // Rien à enregistrer puisque la liste n'a pas changé.
    expect(
      screen.getByRole("button", { name: /Enregistrer les compétences/ }),
    ).toBeDisabled();
  });

  it("lecture seule pour un non-reviewer (pas de contrôle d'édition)", async () => {
    stubFetch("viewer");
    renderPanel();
    await screen.findByText("React");

    expect(screen.queryByLabelText("Ajouter une compétence")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Enregistrer les compétences/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retirer React" })).not.toBeInTheDocument();
    // L'import de CV est aussi une curation → absent pour un non-reviewer (OPP-174).
    expect(screen.queryByLabelText("Importer un CV PDF")).not.toBeInTheDocument();
  });

  it("importe un CV PDF : POST base64 + contract_type, puis profil rafraîchi (OPP-174)", async () => {
    const posts = stubFetchWithCv("reviewer");
    renderPanel();
    await screen.findByText("React");

    // %PDF en octets : on vérifie que le composant les encode bien en base64 dans le corps.
    const file = new File([new Uint8Array([37, 80, 68, 70])], "cv.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(screen.getByLabelText("Importer un CV PDF"), file);

    expect(await screen.findByText("Profil mis à jour depuis le CV.")).toBeInTheDocument();
    expect(posts).toHaveLength(1);
    expect(posts[0].contract_type).toBe("CDI");
    expect(posts[0].pdf_base64).toBe(btoa(String.fromCharCode(37, 80, 68, 70)));
    // Le catalogue étant invalidé, le profil reconstitué s'affiche (nouvelles compétences).
    expect(await screen.findByText("Python")).toBeInTheDocument();
  });

  it("refuse un CV trop volumineux sans l'envoyer (OPP-174)", async () => {
    const posts = stubFetchWithCv("reviewer");
    renderPanel();
    await screen.findByText("React");

    const file = new File([new Uint8Array([37, 80, 68, 70])], "gros-cv.pdf", {
      type: "application/pdf",
    });
    // Taille truquée au-delà de la borne (10 Mo) : inutile d'allouer réellement 10 Mo en test.
    Object.defineProperty(file, "size", { value: 10 * 1024 * 1024 + 1 });
    await userEvent.upload(screen.getByLabelText("Importer un CV PDF"), file);

    expect(await screen.findByText(/CV trop volumineux/)).toBeInTheDocument();
    expect(posts).toHaveLength(0); // aucun encodage ni POST
  });

  it("affiche le parcours extrait du CV (OPP-176)", async () => {
    stubProfile({ ...PROFILE, experiences: [EXPERIENCE] }, "viewer");
    renderPanel();

    // En-tête de section + contenu d'une carte d'expérience.
    expect(await screen.findByText("Parcours")).toBeInTheDocument();
    expect(screen.getByText("Développeuse Fullstack")).toBeInTheDocument();
    expect(screen.getByText(/CBNSA · Gironde/)).toBeInTheDocument();
    expect(screen.getByText("2023 – 2025")).toBeInTheDocument();
    expect(screen.getByText("+45 % de trafic organique")).toBeInTheDocument();
    expect(screen.getByText("Symfony")).toBeInTheDocument();
  });

  it("oriente vers l'import quand le profil est vide (OPP-176)", async () => {
    stubProfile({ ...PROFILE, skills: [], experiences: [] }, "reviewer");
    renderPanel();

    expect(await screen.findByText(/Ton profil est encore vide/)).toBeInTheDocument();
    // Pas de section Parcours quand il n'y a aucune expérience.
    expect(screen.queryByText("Parcours")).not.toBeInTheDocument();
  });

  it("annonce une attente de plusieurs minutes pendant l'analyse (OPP-176)", async () => {
    // POST /profile/cv suspendu : on observe l'état d'attente sans le résoudre.
    let release!: (v: unknown) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        const s = String(url);
        if (s.includes("/me"))
          return ok({ id: "u", role: "reviewer", owned_count: 1, owned_candidate_ids: ["cand-1"] });
        if (s.includes("/profile/cv") && init?.method === "POST")
          return new Promise((r) => { release = r; });
        return ok(PROFILE);
      }),
    );
    renderPanel();
    await screen.findByText("React");

    const file = new File([new Uint8Array([37, 80, 68, 70])], "cv.pdf", {
      type: "application/pdf",
    });
    await userEvent.upload(screen.getByLabelText("Importer un CV PDF"), file);

    expect(await screen.findByText(/l'extraction locale prend 1 à 5 minutes/)).toBeInTheDocument();
    expect(release).toBeDefined(); // la requête est bien partie (et reste en attente)
  });
});
