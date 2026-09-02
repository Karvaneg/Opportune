const { test } = require("node:test");
const assert = require("node:assert/strict");

const { editCoverLetter, editAdaptedResume } = require("./documentEditor");

const PROFILE = {
  name: "Marie",
  structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
  skills: ["JavaScript"],
  experiences: ["Lead React chez Y"],
};

// --- editCoverLetter ---

test("editCoverLetter : correction fidèle → verification.ok", () => {
  const letter = { subject: "Candidature", body: "Solide en React." };
  const { document, verification } = editCoverLetter(letter, { body: "Solide en React et JavaScript." }, PROFILE);
  assert.equal(document.body, "Solide en React et JavaScript.");
  assert.equal(verification.ok, true);
});

test("editCoverLetter : édition introduisant un outil non détenu → signalée", () => {
  const { verification } = editCoverLetter({ body: "" }, { body: "Maîtrise de Kubernetes." }, PROFILE);
  assert.equal(verification.ok, false);
  assert.deepEqual(verification.unsupportedSkills, ["Kubernetes"]);
});

test("editCoverLetter : ne modifie que les champs autorisés", () => {
  const letter = { id: "L1", subject: "A", body: "React" };
  const { document } = editCoverLetter(letter, { subject: "B", id: "HACK" }, PROFILE);
  assert.equal(document.subject, "B");
  assert.equal(document.id, "L1"); // id préservé
});

// --- editAdaptedResume ---

test("editAdaptedResume : retrait d'une compétence → reste fidèle", () => {
  const cv = { skills: [{ name: "React" }, { name: "PostgreSQL" }], experiences: ["Lead React chez Y"] };
  const { document, verification } = editAdaptedResume(cv, { skills: [{ name: "React" }] }, PROFILE);
  assert.deepEqual(document.skills, [{ name: "React" }]);
  assert.equal(verification.ok, true);
});

test("editAdaptedResume : ajout d'une compétence inventée → détecté", () => {
  const cv = { skills: [{ name: "React" }], experiences: [] };
  const { verification } = editAdaptedResume(cv, { skills: [{ name: "React" }, { name: "Kubernetes" }] }, PROFILE);
  assert.equal(verification.ok, false);
  assert.deepEqual(verification.unsupportedSkills, ["Kubernetes"]);
});

test("editAdaptedResume : ajout d'une expérience inventée → détecté", () => {
  const cv = { skills: [{ name: "React" }], experiences: ["Lead React chez Y"] };
  const { verification } = editAdaptedResume(cv, { experiences: ["Lead React chez Y", "CTO chez FictionCorp"] }, PROFILE);
  assert.equal(verification.ok, false);
  assert.deepEqual(verification.unsupportedExperiences, ["CTO chez FictionCorp"]);
});
