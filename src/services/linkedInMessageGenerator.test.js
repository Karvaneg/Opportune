const { test } = require("node:test");
const assert = require("node:assert/strict");

const { generateLinkedInMessage, CONNECTION_NOTE_MAX_LENGTH } = require("./linkedInMessageGenerator");
const { verifyCoverLetter } = require("./inventionGuard");

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

test("generateLinkedInMessage : produit une note de connexion et un InMail", () => {
  const { connectionNote, inMail } = generateLinkedInMessage(PROFILE, OFFER);
  assert.equal(typeof connectionNote, "string");
  assert.ok(connectionNote.length > 0);
  assert.ok(inMail.subject.length > 0);
  assert.ok(inMail.body.length > 0);
});

test("generateLinkedInMessage : mentionne précisément l'entreprise et l'offre", () => {
  const { connectionNote, inMail } = generateLinkedInMessage(PROFILE, OFFER);
  assert.ok(connectionNote.includes("ACME") && connectionNote.includes("Développeur Fullstack"));
  assert.ok(inMail.body.includes("ACME") && inMail.body.includes("Développeur Fullstack"));
  assert.ok(inMail.subject.includes("ACME") && inMail.subject.includes("Développeur Fullstack"));
});

test("generateLinkedInMessage : la note de connexion respecte la limite LinkedIn", () => {
  const { connectionNote } = generateLinkedInMessage(PROFILE, OFFER);
  assert.ok(connectionNote.length <= CONNECTION_NOTE_MAX_LENGTH);
});

test("generateLinkedInMessage : met en avant les compétences réelles, sans rien inventer", () => {
  const { connectionNote, inMail, highlightedSkills } = generateLinkedInMessage(PROFILE, OFFER);
  assert.deepEqual(highlightedSkills, ["React", "PostgreSQL"]);
  assert.ok(inMail.body.includes("React") && inMail.body.includes("PostgreSQL"));
  // Compétence exigée mais non détenue → jamais dans les messages
  assert.ok(!connectionNote.includes("Kubernetes"));
  assert.ok(!inMail.body.includes("Kubernetes"));
});

test("generateLinkedInMessage : compétences vérifiées fidèles par inventionGuard", () => {
  const message = generateLinkedInMessage(PROFILE, OFFER);
  // Le champ highlightedSkills est directement vérifiable par le garde-fou.
  assert.deepEqual(verifyCoverLetter(message, PROFILE), { ok: true, unsupportedSkills: [] });
});

test("generateLinkedInMessage : InMail intègre le contrat et signe avec le nom", () => {
  const { inMail } = generateLinkedInMessage(PROFILE, OFFER);
  assert.ok(inMail.body.includes("CDI comme en freelance"));
  assert.ok(inMail.body.trimEnd().endsWith("Marie Dupont"));
});

test("generateLinkedInMessage : sans compétence pertinente, formulation neutre", () => {
  const profile = { name: "Jean", contractType: "CDI", skills: ["COBOL"] };
  const { connectionNote, inMail, highlightedSkills } = generateLinkedInMessage(profile, OFFER);
  assert.deepEqual(highlightedSkills, []);
  assert.ok(inMail.body.includes("correspond aux attentes de ce poste"));
  assert.ok(connectionNote.includes("a retenu mon attention"));
});

test("generateLinkedInMessage : la clause compétences est omise si elle dépasse la limite", () => {
  // Un intitulé très long pousse la clause compétences hors des 300 caractères.
  const longOffer = {
    ...OFFER,
    title: "Développeur Fullstack Senior spécialisé React, Node.js et architectures distribuées à grande échelle",
  };
  const { connectionNote } = generateLinkedInMessage(PROFILE, longOffer);
  assert.ok(connectionNote.length <= CONNECTION_NOTE_MAX_LENGTH);
  assert.ok(connectionNote.includes("Seriez-vous ouvert(e) à un échange ?"));
});

test("generateLinkedInMessage : entreprise ou intitulé manquant → erreur explicite", () => {
  assert.throws(() => generateLinkedInMessage(PROFILE, { title: "Dev" }), /entreprise/i);
  assert.throws(() => generateLinkedInMessage(PROFILE, { company: "ACME" }), /intitulé/i);
});
