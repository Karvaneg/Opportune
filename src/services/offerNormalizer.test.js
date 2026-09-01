const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  normalizeContractType,
  normalizeOffer,
  normalizeOffers,
} = require("./offerNormalizer");

// --- normalizeContractType ---

test("normalizeContractType : reconnaît les valeurs canoniques et variantes", () => {
  assert.equal(normalizeContractType("cdi"), "CDI");
  assert.equal(normalizeContractType("C.D.I"), "CDI");
  assert.equal(normalizeContractType("CDD"), "CDD");
  assert.equal(normalizeContractType("Freelance"), "FREELANCE");
  assert.equal(normalizeContractType("indépendant"), "FREELANCE");
});

test("normalizeContractType : inconnu ou absent → null", () => {
  assert.equal(normalizeContractType("stage"), null);
  assert.equal(normalizeContractType(""), null);
  assert.equal(normalizeContractType(undefined), null);
});

// --- normalizeOffer ---

test("normalizeOffer : harmonise les alias de champs et trime", () => {
  const offer = normalizeOffer({
    titre: "  Développeur JS  ",
    entreprise: "ACME",
    source: "linkedin",
    lien: "https://x",
    type: "cdd",
    ville: " Nantes ",
  });
  assert.equal(offer.title, "Développeur JS");
  assert.equal(offer.company, "ACME");
  assert.equal(offer.url, "https://x");
  assert.equal(offer.contractType, "CDD");
  assert.equal(offer.location, "Nantes");
});

test("normalizeOffer : champs absents marqués (null / \"\") et id généré", () => {
  const offer = normalizeOffer({ titre: "Dev" });
  assert.equal(offer.company, ""); // obligatoire absent
  assert.equal(offer.location, null); // optionnel absent = non renseigné
  assert.equal(offer.contractType, null);
  assert.ok(offer.id);
});

test("normalizeOffer : conserve les données brutes d'origine", () => {
  const raw = { titre: "Dev", extraSourceField: 42 };
  const offer = normalizeOffer(raw);
  assert.deepEqual(offer.raw, raw);
});

test("normalizeOffers : normalise une liste", () => {
  const offers = normalizeOffers([{ titre: "A", type: "cdi" }, { titre: "B", type: "freelance" }]);
  assert.deepEqual(offers.map((o) => o.contractType), ["CDI", "FREELANCE"]);
});
