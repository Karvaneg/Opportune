const { test } = require("node:test");
const assert = require("node:assert/strict");

const { validateProfile, createValidProfile } = require("./profileService");

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

test("createValidProfile : renvoie un profil complet quand il est valide", () => {
  const profile = createValidProfile({
    name: "Alex",
    skills: ["JavaScript"],
    contractType: "CDI",
  });

  assert.equal(profile.name, "Alex");
  assert.deepEqual(profile.skills, ["JavaScript"]);
  assert.equal(profile.contractType, "CDI");
});

test("createValidProfile : lève une erreur sur un profil invalide", () => {
  assert.throws(() => createValidProfile({}), /obligatoire/);
});
