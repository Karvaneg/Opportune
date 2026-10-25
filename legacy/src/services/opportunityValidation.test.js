const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  VALIDATION_DECISIONS,
  reviewApplication,
  buildValidationMessage,
} = require("./opportunityValidation");
const { saveValidApplication, getApplication } = require("./applicationService");

function tmpFile() {
  return path.join(os.tmpdir(), `validation-${process.hrtime.bigint()}.json`);
}

// --- reviewApplication ---

test("reviewApplication : accepter → Validée", () => {
  const file = tmpFile();
  try {
    const a = saveValidApplication({ profileId: "p", offerId: "o" }, file); // À étudier
    const reviewed = reviewApplication(a.id, "accept", file);
    assert.equal(reviewed.status, "Validée");
    assert.equal(getApplication(a.id, file).status, "Validée");
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("reviewApplication : rejeter → Abandonnée", () => {
  const file = tmpFile();
  try {
    const a = saveValidApplication({ profileId: "p", offerId: "o" }, file);
    assert.equal(reviewApplication(a.id, "reject", file).status, "Abandonnée");
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("reviewApplication : mettre en attente → statut inchangé", () => {
  const file = tmpFile();
  try {
    const a = saveValidApplication({ profileId: "p", offerId: "o" }, file);
    const held = reviewApplication(a.id, "hold", file);
    assert.equal(held.status, "À étudier");
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("reviewApplication : décision inconnue ou candidature absente → erreur", () => {
  const file = tmpFile();
  try {
    const a = saveValidApplication({ profileId: "p", offerId: "o" }, file);
    assert.throws(() => reviewApplication(a.id, "peut-être", file), /inconnue/i);
    assert.throws(() => reviewApplication("inconnu", "hold", file), /introuvable/i);
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("VALIDATION_DECISIONS : accepter, rejeter, mettre en attente", () => {
  assert.deepEqual(VALIDATION_DECISIONS, ["accept", "reject", "hold"]);
});

// --- buildValidationMessage ---

test("buildValidationMessage : agrège offre, score, reco, raisons et actions", () => {
  const offer = { title: "Développeur", company: "ACME" };
  const comparison = {
    skills: { matched: ["React"], missing: ["TypeScript"] },
    contractType: { offer: "CDI", profile: "les deux", compatible: true },
    salary: { status: "ok" },
    experience: { status: "ok", required: 3, profile: 5 },
    location: { status: "match", offer: "Paris" },
    remote: { status: "match", offer: "hybrid" },
    languages: { matched: ["anglais"], missing: [] },
  };

  const message = buildValidationMessage(offer, comparison);

  assert.equal(message.title, "Développeur — ACME");
  assert.ok(typeof message.score === "number");
  assert.ok(message.recommendation.action); // reco présente
  assert.ok(message.positives.some((m) => /React/.test(m)));
  assert.ok(message.negatives.some((m) => /TypeScript/.test(m)));
  assert.deepEqual(message.actions.map((a) => a.decision), ["accept", "reject", "hold"]);
});
