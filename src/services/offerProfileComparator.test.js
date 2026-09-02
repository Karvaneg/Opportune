const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  compareOfferToProfile,
  compareSkills,
  compareContractType,
  compareExperience,
  compareLocation,
  compareRemote,
  compareLanguages,
  compareSalary,
} = require("./offerProfileComparator");

// --- compareSkills ---

test("compareSkills : matched/missing sur vocabulaire canonisé (profil legacy + structuré)", () => {
  const profile = {
    skills: ["JavaScript"], // legacy
    structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }], // canonisé → SQL
  };
  const result = compareSkills(["TypeScript", "React", "SQL"], profile);
  assert.deepEqual(result.matched, ["React", "SQL"]);
  assert.deepEqual(result.missing, ["TypeScript"]);
});

test("compareSkills : offre sans compétence → listes vides", () => {
  assert.deepEqual(compareSkills([], { skills: ["React"] }), { matched: [], missing: [] });
});

// --- compareContractType (normalisation de casse profil↔offre) ---

test("compareContractType : « les deux » accepte CDI et FREELANCE, pas CDD", () => {
  assert.equal(compareContractType("CDI", { contractType: "les deux" }).compatible, true);
  assert.equal(compareContractType("FREELANCE", { contractType: "les deux" }).compatible, true);
  assert.equal(compareContractType("CDD", { contractType: "les deux" }).compatible, false);
});

test("compareContractType : préférence unique", () => {
  assert.equal(compareContractType("CDI", { contractType: "CDI" }).compatible, true);
  assert.equal(compareContractType("FREELANCE", { contractType: "CDI" }).compatible, false);
});

test("compareContractType : donnée manquante → compatible null (inconnu)", () => {
  assert.equal(compareContractType(null, { contractType: "CDI" }).compatible, null);
  assert.equal(compareContractType("CDI", {}).compatible, null);
});

// --- compareExperience ---

test("compareExperience : exigence remontée ou non requise", () => {
  assert.deepEqual(compareExperience(4), { required: 4, status: "unknown" });
  assert.deepEqual(compareExperience(null), { required: null, status: "not_required" });
});

// --- compareLocation ---

test("compareLocation : match, mismatch, inconnu", () => {
  assert.equal(compareLocation("Paris", { location: "paris" }).status, "match");
  assert.equal(compareLocation("Paris", { location: "Lyon" }).status, "mismatch");
  assert.equal(compareLocation("Paris", {}).status, "unknown");
});

test("compareLocation : offre full remote → non bloquant malgré l'écart", () => {
  const result = compareLocation("Paris", { location: "Lyon" }, "remote");
  assert.equal(result.status, "not_blocking");
  assert.equal(result.reason, "offer-remote");
});

test("compareLocation : profil mobile → non bloquant sur écart ou lieu manquant", () => {
  assert.equal(compareLocation("Paris", { location: "Lyon", mobility: "France entière" }, "onsite").status, "not_blocking");
  assert.equal(compareLocation("Paris", { mobility: "Mobile" }).status, "not_blocking");
  // Mobilité restreinte → l'écart reste bloquant
  assert.equal(compareLocation("Paris", { location: "Lyon", mobility: "Lyon uniquement" }).status, "mismatch");
});

test("compareLocation : full remote prime sur une correspondance de lieu", () => {
  assert.equal(compareLocation("Paris", { location: "Paris" }, "remote").reason, "offer-remote");
});

// --- compareRemote (réutilise l'heuristique de l'extracteur) ---

test("compareRemote : normalise le souhait libre du profil puis compare", () => {
  assert.equal(compareRemote("hybrid", { remote: "hybride" }).status, "match");
  assert.equal(compareRemote("remote", { remote: "présentiel" }).status, "mismatch");
  assert.equal(compareRemote("hybrid", {}).status, "unknown");
});

// --- compareLanguages ---

test("compareLanguages : canonise les langues du profil (English → anglais)", () => {
  const result = compareLanguages(["anglais", "allemand"], { languages: ["Français", "English"] });
  assert.deepEqual(result.matched, ["anglais"]);
  assert.deepEqual(result.missing, ["allemand"]);
});

// --- compareSalary ---

test("compareSalary : annuel ok / below selon la cible", () => {
  const offer = { min: 45000, max: 60000, period: "year" };
  assert.equal(compareSalary(offer, { targetSalary: 55000 }).status, "ok");
  assert.equal(compareSalary(offer, { targetSalary: 70000 }).status, "below");
});

test("compareSalary : TJM sur targetDailyRate ; cible absente → inconnu", () => {
  assert.equal(compareSalary({ min: 500, max: 500, period: "day" }, { targetDailyRate: 450 }).status, "ok");
  assert.equal(compareSalary({ min: 500, max: 500, period: "day" }, {}).status, "unknown");
  assert.equal(compareSalary(null, { targetSalary: 50000 }).status, "unknown");
});

// --- compareOfferToProfile (intégration) ---

test("compareOfferToProfile : agrège toutes les dimensions", () => {
  const offerKeyInfo = {
    skills: ["TypeScript", "React", "SQL"],
    contractType: "CDI",
    experienceYears: 4,
    location: "Paris",
    salary: { min: 45000, max: 60000, period: "year" },
    remote: "hybrid",
    languages: ["anglais"],
    constraints: [],
  };
  const profile = {
    name: "Marie",
    skills: ["JavaScript"],
    structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
    contractType: "les deux",
    location: "Paris",
    remote: "hybride",
    targetSalary: 55000,
    targetDailyRate: null,
    languages: ["Français", "Anglais"],
  };

  const report = compareOfferToProfile(offerKeyInfo, profile);

  assert.deepEqual(report.skills, { matched: ["React", "SQL"], missing: ["TypeScript"] });
  assert.equal(report.contractType.compatible, true);
  assert.deepEqual(report.experience, { required: 4, status: "unknown" });
  assert.equal(report.location.status, "match");
  assert.equal(report.remote.status, "match");
  assert.deepEqual(report.languages, { matched: ["anglais"], missing: [] });
  assert.equal(report.salary.status, "ok");
});

test("compareOfferToProfile : entrées vides → dimensions neutres", () => {
  const report = compareOfferToProfile({}, {});
  assert.deepEqual(report.skills, { matched: [], missing: [] });
  assert.equal(report.contractType.compatible, null);
  assert.equal(report.experience.status, "not_required");
  assert.equal(report.location.status, "unknown");
  assert.equal(report.remote.status, "unknown");
  assert.deepEqual(report.languages, { matched: [], missing: [] });
  assert.equal(report.salary.status, "unknown");
});
