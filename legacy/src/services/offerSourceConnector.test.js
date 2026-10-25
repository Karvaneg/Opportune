const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createSourceConnector } = require("./offerSourceConnector");

// Logger de test : collecte les messages d'erreur au lieu de les afficher.
function silentLogger() {
  const errors = [];
  return { errors, error: (msg) => errors.push(msg) };
}

// Offre CDI brute valide (champs hétérogènes, testent la normalisation).
function rawCdiOffer(overrides = {}) {
  return {
    titre: "Développeur Node.js",
    entreprise: "ACME",
    url: "https://example.com/offre/1",
    contractType: "contrat à durée indéterminée",
    ...overrides,
  };
}

// --- Configuration ---

test("createSourceConnector : exige un nom de source", () => {
  assert.throws(() => createSourceConnector({ fetcher: () => [] }), /nom de source/);
});

test("createSourceConnector : exige un fetcher fonction", () => {
  assert.throws(() => createSourceConnector({ name: "apec" }), /fetcher/);
});

test("createSourceConnector : rejette un type de contrat de filtre invalide", () => {
  assert.throws(
    () => createSourceConnector({ name: "apec", fetcher: () => [], contractType: "STAGE" }),
    /invalide/,
  );
});

test("createSourceConnector : expose nom et filtre", () => {
  const connector = createSourceConnector({ name: "  apec  ", fetcher: () => [], contractType: "CDI" });
  assert.equal(connector.name, "apec"); // trimé
  assert.equal(connector.contractType, "CDI");
});

// --- Récupération et normalisation ---

test("fetchOffers : normalise vers le modèle jobOffer et conserve url + source", async () => {
  const connector = createSourceConnector({
    name: "apec",
    fetcher: () => [rawCdiOffer()],
    logger: silentLogger(),
  });

  const { offers, skipped } = await connector.fetchOffers();

  assert.equal(offers.length, 1);
  assert.equal(skipped.length, 0);
  const [offer] = offers;
  assert.equal(offer.title, "Développeur Node.js");
  assert.equal(offer.company, "ACME");
  assert.equal(offer.url, "https://example.com/offre/1"); // URL conservée
  assert.equal(offer.source, "apec"); // source d'origine imposée par le connecteur
  assert.equal(offer.contractType, "CDI"); // normalisé
  assert.ok(offer.id); // exploitable pour analyse/scoring/persistance
  assert.deepEqual(offer.raw, { ...rawCdiOffer(), source: "apec" }); // traçabilité
});

test("fetchOffers : supporte un fetcher asynchrone", async () => {
  const connector = createSourceConnector({
    name: "apec",
    fetcher: async () => [rawCdiOffer()],
    logger: silentLogger(),
  });

  const { offers } = await connector.fetchOffers();
  assert.equal(offers.length, 1);
});

test("fetchOffers : transmet les paramètres au fetcher", async () => {
  let received;
  const connector = createSourceConnector({
    name: "apec",
    fetcher: (params) => {
      received = params;
      return [];
    },
    logger: silentLogger(),
  });

  await connector.fetchOffers({ query: "node", location: "Rennes" });
  assert.deepEqual(received, { query: "node", location: "Rennes" });
});

// --- Filtre de type de contrat (source CDI) ---

test("fetchOffers : filtre les offres hors du type de contrat configuré", async () => {
  const connector = createSourceConnector({
    name: "apec",
    contractType: "CDI",
    fetcher: () => [
      rawCdiOffer(),
      rawCdiOffer({ contractType: "freelance", url: "https://example.com/offre/2" }),
    ],
    logger: silentLogger(),
  });

  const { offers, skipped } = await connector.fetchOffers();
  assert.equal(offers.length, 1);
  assert.equal(offers[0].contractType, "CDI");
  assert.equal(skipped.length, 1);
  assert.equal(skipped[0].reason, "contractType");
});

// --- Offres invalides ---

test("fetchOffers : écarte et journalise les offres invalides sans casser le lot", async () => {
  const logger = silentLogger();
  const connector = createSourceConnector({
    name: "apec",
    fetcher: () => [
      rawCdiOffer(),
      { titre: "Sans URL ni entreprise" }, // invalide : url, company, contractType manquants
    ],
    logger,
  });

  const { offers, skipped } = await connector.fetchOffers();
  assert.equal(offers.length, 1); // l'offre valide reste disponible
  assert.equal(skipped.length, 1);
  assert.equal(skipped[0].reason, "invalid");
  assert.ok(skipped[0].errors.length > 0);
  assert.ok(logger.errors.some((m) => m.includes("invalide")));
});

// --- Erreurs de récupération ---

test("fetchOffers : journalise puis propage une erreur du fetcher", async () => {
  const logger = silentLogger();
  const connector = createSourceConnector({
    name: "apec",
    fetcher: () => {
      throw new Error("réseau indisponible");
    },
    logger,
  });

  await assert.rejects(() => connector.fetchOffers(), /réseau indisponible/);
  assert.ok(logger.errors.some((m) => m.includes("échec de récupération")));
});

test("fetchOffers : rejette un fetcher qui ne renvoie pas un tableau", async () => {
  const logger = silentLogger();
  const connector = createSourceConnector({
    name: "apec",
    fetcher: () => ({ not: "an array" }),
    logger,
  });

  await assert.rejects(() => connector.fetchOffers(), /tableau/);
});
