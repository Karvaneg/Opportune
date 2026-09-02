const { test } = require("node:test");
const assert = require("node:assert/strict");

const { SAMPLE_RAW_OFFERS, sampleOffers } = require("./sampleOffers");
const { validateOffer } = require("../services/offerService");
const { classifyOpportunity } = require("../services/opportunityClassifier");

test("sampleOffers : toutes les offres normalisées sont valides", () => {
  for (const offer of sampleOffers()) {
    const { valid, errors } = validateOffer(offer);
    assert.ok(valid, `offre invalide (${offer.id}) : ${errors.join(", ")}`);
  }
});

test("sampleOffers : ids uniques et jeu non trivial", () => {
  const offers = sampleOffers();
  assert.ok(offers.length >= 5);
  const ids = offers.map((o) => o.id);
  assert.equal(new Set(ids).size, ids.length);
});

test("sampleOffers : couvre les trois types de contrat", () => {
  const types = new Set(sampleOffers().map((o) => o.contractType));
  assert.ok(types.has("CDI"));
  assert.ok(types.has("CDD"));
  assert.ok(types.has("FREELANCE"));
});

test("sampleOffers : couvre CDI/CDD/Freelance et le cas À ignorer (profil dev CDI/freelance)", () => {
  const profile = { contractType: "les deux" };
  const categories = new Set(sampleOffers().map((o) => classifyOpportunity(o, profile)));
  assert.ok(categories.has("CDI"));
  assert.ok(categories.has("Freelance"));
  assert.ok(categories.has("À ignorer")); // le CDD est écarté pour ce profil
});

test("SAMPLE_RAW_OFFERS : données brutes hétérogènes conservées après normalisation", () => {
  const offer = sampleOffers().find((o) => o.id === "sample-2");
  assert.equal(offer.contractType, "FREELANCE"); // « Freelance » normalisé
  assert.equal(offer.company, "DataCorp"); // alias « client »
  assert.ok(offer.raw); // données d'origine tracées
});
