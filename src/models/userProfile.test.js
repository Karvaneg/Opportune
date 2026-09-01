const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createProfile, updateProfile, CONTRACT_TYPES } = require("./userProfile");

test("createProfile : défauts neutres pour les champs absents", () => {
  const p = createProfile();
  assert.equal(p.name, "");
  assert.deepEqual(p.skills, []);
  assert.equal(p.contractType, null);
  assert.deepEqual(p.languages, []);
});

test("createProfile : conserve les valeurs fournies", () => {
  const p = createProfile({ name: "Alex", skills: ["JS"], contractType: "CDI" });
  assert.equal(p.name, "Alex");
  assert.deepEqual(p.skills, ["JS"]);
  assert.ok(CONTRACT_TYPES.includes(p.contractType));
});

test("updateProfile : applique les changements sans muter l'original", () => {
  const p = createProfile({ name: "Alex" });
  const updated = updateProfile(p, { name: "Sam", remote: "hybride" });
  assert.equal(updated.name, "Sam");
  assert.equal(updated.remote, "hybride");
  assert.equal(p.name, "Alex"); // l'original reste intact
});
