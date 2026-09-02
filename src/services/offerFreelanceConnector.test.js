const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createFreelanceConnector, extractFreelanceDetails } = require("./offerFreelanceConnector");

// Logger de test : collecte les messages d'erreur au lieu de les afficher.
function silentLogger() {
  const errors = [];
  return { errors, error: (msg) => errors.push(msg) };
}

// Mission freelance brute valide (champs hétérogènes).
function rawMission(overrides = {}) {
  return {
    titre: "Mission Node.js",
    client: "ACME",
    url: "https://malt.fr/mission/1",
    contractType: "freelance",
    tjm: "550€/j",
    duree: "6 mois",
    disponibilité: "immédiate",
    ...overrides,
  };
}

// --- extractFreelanceDetails ---

test("extractFreelanceDetails : extrait budget, TJM, durée et disponibilité", () => {
  const details = extractFreelanceDetails(rawMission());
  assert.equal(details.tjm, "550€/j");
  assert.equal(details.duration, "6 mois");
  assert.equal(details.availability, "immédiate");
  assert.equal(details.budget, null); // absent → null
});

test("extractFreelanceDetails : champs absents → null", () => {
  assert.deepEqual(extractFreelanceDetails({}), {
    budget: null,
    tjm: null,
    duration: null,
    availability: null,
  });
});

test("extractFreelanceDetails : reconnaît les alias (dailyRate, duration, startDate)", () => {
  const details = extractFreelanceDetails({
    budget: "30k€",
    dailyRate: "600",
    duration: "3 months",
    startDate: "2026-10-01",
  });
  assert.equal(details.budget, "30k€");
  assert.equal(details.tjm, "600");
  assert.equal(details.duration, "3 months");
  assert.equal(details.availability, "2026-10-01");
});

// --- Configuration ---

test("createFreelanceConnector : exige une plateforme", () => {
  assert.throws(() => createFreelanceConnector({ fetcher: () => [] }), /plateforme/);
});

test("createFreelanceConnector : force le type de contrat FREELANCE", () => {
  const connector = createFreelanceConnector({ platform: "malt", fetcher: () => [] });
  assert.equal(connector.platform, "malt");
  assert.equal(connector.contractType, "FREELANCE");
});

// --- Récupération et enrichissement ---

test("fetchOffers : normalise, conserve url/source et attache les détails freelance", async () => {
  const connector = createFreelanceConnector({
    platform: "malt",
    fetcher: () => [rawMission()],
    logger: silentLogger(),
  });

  const { offers, skipped } = await connector.fetchOffers();

  assert.equal(offers.length, 1);
  assert.equal(skipped.length, 0);
  const [mission] = offers;
  assert.equal(mission.title, "Mission Node.js");
  assert.equal(mission.company, "ACME");
  assert.equal(mission.url, "https://malt.fr/mission/1"); // URL conservée
  assert.equal(mission.source, "malt"); // source d'origine imposée
  assert.equal(mission.contractType, "FREELANCE");
  assert.equal(mission.compensation, "550€/j"); // TJM mappé sur compensation (modèle OPP-020)
  assert.deepEqual(mission.freelance, {
    budget: null,
    tjm: "550€/j",
    duration: "6 mois",
    availability: "immédiate",
  });
});

test("fetchOffers : supporte un fetcher asynchrone", async () => {
  const connector = createFreelanceConnector({
    platform: "malt",
    fetcher: async () => [rawMission()],
    logger: silentLogger(),
  });
  const { offers } = await connector.fetchOffers();
  assert.equal(offers.length, 1);
});

// --- Filtre FREELANCE hérité du connecteur générique ---

test("fetchOffers : écarte les offres qui ne sont pas en freelance", async () => {
  const connector = createFreelanceConnector({
    platform: "malt",
    fetcher: () => [
      rawMission(),
      rawMission({ contractType: "CDI", url: "https://malt.fr/mission/2" }),
    ],
    logger: silentLogger(),
  });

  const { offers, skipped } = await connector.fetchOffers();
  assert.equal(offers.length, 1);
  assert.equal(offers[0].contractType, "FREELANCE");
  assert.equal(skipped.length, 1);
  assert.equal(skipped[0].reason, "contractType");
});

// --- Erreurs de récupération (héritées) ---

test("fetchOffers : journalise puis propage une erreur du fetcher", async () => {
  const logger = silentLogger();
  const connector = createFreelanceConnector({
    platform: "malt",
    fetcher: () => {
      throw new Error("plateforme indisponible");
    },
    logger,
  });

  await assert.rejects(() => connector.fetchOffers(), /plateforme indisponible/);
  assert.ok(logger.errors.some((m) => m.includes("échec de récupération")));
});
