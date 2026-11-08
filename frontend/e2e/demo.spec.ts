import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// Parcours réels dans l'espace Démo (OPP-244) : front compilé + vraie API + base démo seedée.
// Aucun appel au LLM ni au réseau : la vitrine (5 offres, décisions, une candidature, une lettre)
// est posée par le seed. Chaque scénario part de la vitrine canonique.

/** Remet la démo dans son état d'origine puis ouvre l'espace Démo depuis l'écran d'accueil. */
async function openDemo(page: Page, request: APIRequestContext) {
  const restored = await request.post("/api/demo/restore");
  expect(restored.ok()).toBe(true);
  await page.goto("/");
  await page.getByRole("button", { name: /Démo/ }).click();
  await expect(page.getByText("Espace démo")).toBeVisible();
}

/** Ouvre la fiche de l'offre « Data Engineer » (à étudier dans la vitrine). */
async function openDataEngineer(page: Page) {
  await page.getByRole("link", { name: "Offres", exact: true }).click();
  await page.getByRole("button", { name: "Data Engineer" }).click();
}

/** Crée une recherche depuis le sélecteur global ; l'app bascule dessus. */
async function createSearch(page: Page, label: string) {
  await page.getByRole("button", { name: "Nouvelle recherche" }).click();
  await page.getByLabel("Nom de la recherche").fill(label);
  await page.getByRole("button", { name: "Créer" }).click();
}

test.beforeEach(async ({ page, request }) => {
  await openDemo(page, request);
});

test("l'accueil affiche les compteurs et les dernières activités de la vitrine", async ({
  page,
}) => {
  await expect(page.getByText("5 offre(s) au total")).toBeVisible();
  await expect(page.getByRole("button", { name: "2 À étudier" })).toBeVisible();
  await expect(page.getByText("Candidature déclarée — Développeuse Python Senior")).toBeVisible();
});

test("une décision prise sur une fiche s'affiche aussitôt", async ({ page }) => {
  await openDataEngineer(page);

  await page.getByRole("button", { name: "Approuver" }).click();

  await expect(page.getByText("Approuvé").first()).toBeVisible();
});

test("une décision prise sur une fiche est enregistrée côté serveur", async ({ page }) => {
  await openDataEngineer(page);
  await page.getByRole("button", { name: "Approuver" }).click();
  await expect(page.getByText("Approuvé").first()).toBeVisible();

  await page.reload();

  await expect(page.getByText("Approuvé").first()).toBeVisible();
});

test("après une décision, le retour ramène à la liste filtrée, à jour", async ({ page }) => {
  await page.goto("/offres?stage=a_etudier");
  await expect(page.getByText("Page 1 / 1 · 2 au total")).toBeVisible();
  await page.getByRole("button", { name: "Data Engineer" }).click();
  await page.getByRole("button", { name: "Approuver" }).click();
  await expect(page.getByText("Approuvé").first()).toBeVisible();

  await page.getByRole("link", { name: "← Retour" }).click();

  await expect(page).toHaveURL(/\/offres\?stage=a_etudier/);
  await expect(page.getByText("Filtré : À étudier")).toBeVisible();
  await expect(page.getByText("Page 1 / 1 · 1 au total")).toBeVisible();
  await expect(page.getByRole("button", { name: "Data Engineer" })).toHaveCount(0);
});

test("une page au-delà de la dernière est ramenée à la dernière", async ({ page }) => {
  await page.goto("/offres?page=50");

  await expect(page.getByText("Page 1 / 1 · 5 au total")).toBeVisible();
});

test("une nouvelle recherche affiche l'étape « Récupérer des offres » à faire", async ({ page }) => {
  await createSearch(page, "Recherche vide");

  await expect(page.getByLabel("Nouveau profil")).toBeVisible();
  await expect(page.getByRole("link", { name: "Récupérer des offres" })).toBeVisible();
});

test("une nouvelle recherche a une bibliothèque d'offres vide", async ({ page }) => {
  await createSearch(page, "Recherche vide");
  await expect(page.getByLabel("Nouveau profil")).toBeVisible();

  await page.getByRole("link", { name: "Offres", exact: true }).click();

  await expect(page.getByText(/Aucune offre dans le catalogue/)).toBeVisible();
});
