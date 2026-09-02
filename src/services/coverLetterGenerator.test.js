const { test } = require("node:test");
const assert = require("node:assert/strict");

const { generateCoverLetter } = require("./coverLetterGenerator");

const PROFILE = {
  name: "Marie Dupont",
  contractType: "les deux",
  structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
  skills: ["JavaScript"],
};

const OFFER = {
  title: "Développeur Fullstack",
  company: "ACME",
  source: "linkedin",
  contractType: "CDI",
  description: "Stack React et SQL. Kubernetes souhaité.", // Kubernetes non détenu
};

test("generateCoverLetter : mentionne précisément l'entreprise et l'offre (critère)", () => {
  const { subject, body } = generateCoverLetter(PROFILE, OFFER);
  assert.ok(body.includes("ACME"));
  assert.ok(body.includes("Développeur Fullstack"));
  assert.ok(subject.includes("ACME") && subject.includes("Développeur Fullstack"));
});

test("generateCoverLetter : met en avant les compétences réelles, sans rien inventer", () => {
  const { body, highlightedSkills } = generateCoverLetter(PROFILE, OFFER);
  assert.deepEqual(highlightedSkills, ["React", "PostgreSQL"]);
  assert.ok(body.includes("React") && body.includes("PostgreSQL"));
  // Compétence exigée mais non détenue → jamais dans la lettre
  assert.ok(!body.includes("Kubernetes"));
});

test("generateCoverLetter : intègre le contrat et signe avec le nom", () => {
  const { body } = generateCoverLetter(PROFILE, OFFER);
  assert.ok(body.includes("CDI comme en freelance"));
  assert.ok(body.trimEnd().endsWith("Marie Dupont"));
});

test("generateCoverLetter : sans compétence pertinente, formulation neutre", () => {
  const profile = { name: "Jean", contractType: "CDI", skills: ["COBOL"] };
  const { body } = generateCoverLetter(profile, OFFER);
  assert.ok(body.includes("correspond aux attentes de votre offre"));
  assert.ok(body.includes("un poste en CDI"));
});

test("generateCoverLetter : entreprise ou intitulé manquant → erreur explicite", () => {
  assert.throws(() => generateCoverLetter(PROFILE, { title: "Dev" }), /entreprise/i);
  assert.throws(() => generateCoverLetter(PROFILE, { company: "ACME" }), /intitulé/i);
});
