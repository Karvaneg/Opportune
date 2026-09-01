const { test } = require("node:test");
const assert = require("node:assert/strict");

const { validateProfile } = require("./profileService");

test("valide un profil complet", () => {
  const result = validateProfile({
    name: "Alex",
    skills: ["JavaScript"],
    contractType: "CDI",
  });

  assert.equal(result.valid, true);
});

test("refuse un profil incomplet", () => {
  const result = validateProfile({});

  assert.equal(result.valid, false);
  assert.ok(result.errors.length > 0);
});

test("refuse un type de contrat inconnu", () => {
  const result = validateProfile({
    name: "Alex",
    skills: ["JavaScript"],
    contractType: "stage",
  });

  assert.equal(result.valid, false);
  assert.ok(result.errors.includes("Le type de contrat est invalide"));
});
