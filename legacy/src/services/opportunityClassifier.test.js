const { test } = require("node:test");
const assert = require("node:assert/strict");

const { OPPORTUNITY_CATEGORIES, classifyOpportunity } = require("./opportunityClassifier");

test("classifyOpportunity : type compatible avec les préférences → catégorie du type", () => {
  assert.equal(classifyOpportunity({ contractType: "CDI" }, { contractType: "les deux" }), "CDI");
  assert.equal(classifyOpportunity({ contractType: "FREELANCE" }, { contractType: "les deux" }), "Freelance");
  assert.equal(classifyOpportunity({ contractType: "CDI" }, { contractType: "CDI" }), "CDI");
});

test("classifyOpportunity : type hors préférences → À ignorer", () => {
  // Le profil ne vise pas le CDD
  assert.equal(classifyOpportunity({ contractType: "CDD" }, { contractType: "les deux" }), "À ignorer");
  // Freelance alors que le profil ne veut que du CDI
  assert.equal(classifyOpportunity({ contractType: "FREELANCE" }, { contractType: "CDI" }), "À ignorer");
});

test("classifyOpportunity : profil sans préférence → classé selon le type (CDD atteignable)", () => {
  assert.equal(classifyOpportunity({ contractType: "CDD" }, {}), "CDD");
  assert.equal(classifyOpportunity({ contractType: "CDI" }, {}), "CDI");
});

test("classifyOpportunity : type absent ou non reconnu → À ignorer", () => {
  assert.equal(classifyOpportunity({ contractType: null }, { contractType: "les deux" }), "À ignorer");
  assert.equal(classifyOpportunity({ contractType: "STAGE" }, {}), "À ignorer");
  assert.equal(classifyOpportunity({}, {}), "À ignorer");
});

test("toute classification appartient à l'échelle des catégories", () => {
  const cases = [
    classifyOpportunity({ contractType: "CDI" }, { contractType: "les deux" }),
    classifyOpportunity({ contractType: "CDD" }, {}),
    classifyOpportunity({ contractType: "STAGE" }, {}),
  ];
  for (const category of cases) assert.ok(OPPORTUNITY_CATEGORIES.includes(category));
});
