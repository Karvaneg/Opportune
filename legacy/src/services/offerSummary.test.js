const { test } = require("node:test");
const assert = require("node:assert/strict");

const { summarizeOffer } = require("./offerSummary");

const OFFER = {
  title: "Développeur Fullstack",
  company: "ACME",
  contractType: "CDI",
  location: "Paris",
  description: "Stack React et SQL. TypeScript requis. Déplacements fréquents. Anglais courant.",
};

const PROFILE = {
  name: "Marie Dupont",
  contractType: "les deux",
  structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
  skills: ["JavaScript"],
  location: "Paris",
  languages: ["Français", "Anglais"],
  totalExperienceYears: 5,
};

test("summarizeOffer : contient score, raisons, risques et documents (critère)", () => {
  const summary = summarizeOffer(OFFER, PROFILE);

  // score
  assert.ok(typeof summary.score === "number" && summary.score >= 0 && summary.score <= 100);

  // raisons
  assert.ok(summary.reasons.positives.some((m) => /React/.test(m)));
  assert.ok(summary.reasons.negatives.some((m) => /TypeScript/.test(m)));

  // risques : contrainte de l'offre + compétence manquante
  assert.ok(summary.risks.some((r) => /déplacements/i.test(r)));
  assert.ok(summary.risks.some((r) => /TypeScript/.test(r)));

  // documents : CV adapté + lettre
  const docTypes = summary.documents.map((d) => d.type);
  assert.ok(docTypes.includes("CV adapté"));
  assert.ok(docTypes.includes("Lettre de motivation"));
  const letter = summary.documents.find((d) => d.type === "Lettre de motivation");
  assert.ok(letter.subject.includes("ACME"));
});

test("summarizeOffer : en-tête et recommandation présents", () => {
  const summary = summarizeOffer(OFFER, PROFILE);
  assert.equal(summary.offer.company, "ACME");
  assert.equal(summary.offer.contractType, "CDI");
  assert.ok(summary.recommendation.action);
});

test("summarizeOffer : contrat non désiré remonté comme risque", () => {
  const summary = summarizeOffer({ ...OFFER, contractType: "CDD" }, PROFILE);
  assert.ok(summary.risks.some((r) => /contrat non désiré/i.test(r)));
});

test("summarizeOffer : sans entreprise/intitulé → documents sans lettre, pas d'erreur", () => {
  const summary = summarizeOffer({ description: "React et SQL" }, PROFILE);
  const docTypes = summary.documents.map((d) => d.type);
  assert.deepEqual(docTypes, ["CV adapté"]);
});
