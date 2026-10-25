const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createProfile, updateProfile, CONTRACT_TYPES } = require("./userProfile");
const { createResume } = require("./resume");

test("createProfile : défauts neutres pour les champs absents", () => {
  const p = createProfile();
  assert.ok(p.id); // id stable généré
  assert.equal(p.name, "");
  assert.deepEqual(p.skills, []);
  assert.equal(p.contractType, null);
  assert.deepEqual(p.languages, []);
});

test("createProfile : id généré unique, ou conservé si fourni", () => {
  assert.notEqual(createProfile().id, createProfile().id); // deux ids distincts
  assert.equal(createProfile({ id: "fixed" }).id, "fixed"); // id fourni conservé
});

test("createProfile : champs complémentaires par défaut à null", () => {
  const p = createProfile();
  assert.equal(p.location, null);
  assert.equal(p.availability, null);
  assert.equal(p.targetSalary, null);
  assert.equal(p.targetDailyRate, null);
});

test("createProfile : conserve les valeurs fournies", () => {
  const p = createProfile({ name: "Alex", skills: ["JS"], contractType: "CDI" });
  assert.equal(p.name, "Alex");
  assert.deepEqual(p.skills, ["JS"]);
  assert.ok(CONTRACT_TYPES.includes(p.contractType));
});

test("updateProfile : applique les changements, préserve l'id, sans muter l'original", () => {
  const p = createProfile({ name: "Alex" });
  const updated = updateProfile(p, { name: "Sam", remote: "hybride", id: "hack" });
  assert.equal(updated.name, "Sam");
  assert.equal(updated.remote, "hybride");
  assert.equal(updated.id, p.id); // id stable malgré la tentative de le changer
  assert.equal(p.name, "Alex"); // l'original reste intact
});

test("l'id du profil peut servir de profileId à un CV", () => {
  const profile = createProfile({ name: "Alex" });
  const resume = createResume({ profileId: profile.id, name: "CV" });
  assert.equal(resume.profileId, profile.id);
});
