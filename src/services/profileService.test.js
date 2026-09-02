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

test("valide totalExperienceYears fourni (nombre positif) et refuse une valeur négative", () => {
  const base = { name: "Alex", skills: ["JavaScript"], contractType: "CDI" };
  assert.equal(validateProfile({ ...base, totalExperienceYears: 5 }).valid, true);

  const bad = validateProfile({ ...base, totalExperienceYears: -2 });
  assert.equal(bad.valid, false);
  assert.ok(bad.errors.some((e) => /expérience/.test(e)));
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

// --- OPP-015 : champs complémentaires (facultatifs, validés si fournis) ---

const base = { name: "Alex", skills: ["JavaScript"], contractType: "les deux" };

test("accepte les champs complémentaires valides", () => {
  const result = validateProfile({
    ...base,
    location: "Nantes",
    availability: "sous 1 mois",
    targetSalary: 55000,
    targetDailyRate: 500,
  });
  assert.equal(result.valid, true);
});

test("disponibilité : accepte une option de l'échelle ou une date ISO", () => {
  assert.equal(validateProfile({ ...base, availability: "immédiate" }).valid, true);
  assert.equal(validateProfile({ ...base, availability: "2026-10-01" }).valid, true);
});

test("disponibilité : refuse une valeur hors échelle / date invalide", () => {
  assert.equal(validateProfile({ ...base, availability: "bientôt" }).valid, false);
  assert.equal(validateProfile({ ...base, availability: "2026-13-40" }).valid, false);
});

test("salaire / TJM : refusent une valeur négative ou non numérique", () => {
  assert.equal(validateProfile({ ...base, targetSalary: -1 }).valid, false);
  assert.equal(validateProfile({ ...base, targetDailyRate: "cher" }).valid, false);
  assert.equal(validateProfile({ ...base, targetSalary: 0 }).valid, true); // zéro accepté
});

test("localisation : refuse une chaîne vide fournie", () => {
  assert.equal(validateProfile({ ...base, location: "   " }).valid, false);
});

test("rétrocompatibilité : un profil minimal (sans champs complémentaires) reste valide", () => {
  const legacy = { name: "Alex", skills: ["JavaScript"], contractType: "CDI" };
  assert.equal(validateProfile(legacy).valid, true);
});

test("rétrocompatibilité : un champ obsolète (minCompensation) n'invalide pas le profil", () => {
  const result = validateProfile({ ...base, minCompensation: 50000 });
  assert.equal(result.valid, true);
});
