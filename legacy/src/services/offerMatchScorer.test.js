const { test } = require("node:test");
const assert = require("node:assert/strict");

const { scoreMatch, scoreOfferToProfile } = require("./offerMatchScorer");

// Rapport de comparaison entièrement favorable et évaluable.
const PERFECT = {
  skills: { matched: ["React"], missing: [] },
  contractType: { compatible: true },
  salary: { status: "ok" },
  experience: { status: "ok" },
  location: { status: "match" },
  remote: { status: "match" },
  languages: { matched: ["anglais"], missing: [] },
};

// --- Bornes ---

test("scoreMatch : rapport parfait → 100", () => {
  assert.equal(scoreMatch(PERFECT).score, 100);
});

test("scoreMatch : rapport entièrement défavorable → 0", () => {
  const worst = {
    skills: { matched: [], missing: ["React"] },
    contractType: { compatible: false },
    salary: { status: "below" },
    experience: { status: "insufficient" },
    location: { status: "mismatch" },
    remote: { status: "mismatch" },
    languages: { matched: [], missing: ["anglais"] },
  };
  assert.equal(scoreMatch(worst).score, 0);
});

test("scoreMatch : score toujours borné 0-100 (entier)", () => {
  const { score } = scoreMatch(PERFECT);
  assert.ok(Number.isInteger(score) && score >= 0 && score <= 100);
});

// --- Renormalisation sur les dimensions évaluables ---

test("scoreMatch : les dimensions inconnues sont exclues (renormalisation)", () => {
  // Seules les compétences sont évaluables (couverture totale) → 100
  const comparison = {
    skills: { matched: ["React", "SQL"], missing: [] },
    contractType: { compatible: null },
    salary: { status: "unknown" },
    experience: { status: "unknown" },
    location: { status: "unknown" },
    remote: { status: "unknown" },
    languages: { matched: [], missing: [] },
  };
  const { score, breakdown } = scoreMatch(comparison);
  assert.equal(score, 100);
  assert.equal(breakdown.skills.evaluated, true);
  assert.equal(breakdown.salary.evaluated, false);
  assert.equal(breakdown.languages.evaluated, false); // aucune langue exigée
});

test("scoreMatch : rapport vide → 0 (rien d'évaluable)", () => {
  assert.equal(scoreMatch({}).score, 0);
});

// --- Effets attendus ---

test("scoreMatch : couverture partielle des compétences", () => {
  const { score } = scoreMatch({ skills: { matched: ["React"], missing: ["Vue.js", "SQL"] } });
  assert.equal(score, 33); // 1/3
});

test("scoreMatch : un contrat incompatible coûte son poids (20 pts)", () => {
  // Tout favorable sauf le contrat → 80
  const { score } = scoreMatch({ ...PERFECT, contractType: { compatible: false } });
  assert.equal(score, 80);
});

// --- Intégration depuis offre + profil ---

test("scoreOfferToProfile : de bout en bout sur une offre et un profil", () => {
  const offerKeyInfo = {
    skills: ["TypeScript", "React", "SQL"],
    contractType: "CDI",
    experienceYears: 4, // profil sans total → dimension exclue
    location: "Paris",
    salary: { min: 45000, max: 60000, period: "year" },
    remote: "hybrid",
    languages: ["anglais"],
    constraints: [],
  };
  const profile = {
    skills: ["JavaScript"],
    structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
    contractType: "les deux",
    location: "Paris",
    remote: "hybride",
    targetSalary: 55000,
    languages: ["Français", "Anglais"],
  };

  const { score, breakdown } = scoreOfferToProfile(offerKeyInfo, profile);

  // skills 2/3, contrat/lieu/remote/langues/salaire OK, expérience non évaluée
  assert.equal(score, 87);
  assert.equal(breakdown.experience.evaluated, false);
});
