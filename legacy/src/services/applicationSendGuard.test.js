const { test } = require("node:test");
const assert = require("node:assert/strict");

const { BLOCK_REASONS, authorizeSend, performSend } = require("./applicationSendGuard");

const PROFILE = {
  name: "Marie",
  structuredSkills: [{ name: "React" }, { name: "PostgreSQL" }],
  skills: ["JavaScript"],
  experiences: ["Lead React chez Y"],
};

const FAITHFUL = {
  profile: PROFILE,
  adaptedResume: { skills: [{ name: "React" }], experiences: ["Lead React chez Y"] },
  coverLetter: { highlightedSkills: ["React"] },
};

const CONFIRMED = { confirmed: true };

// --- authorizeSend ---

test("authorizeSend : sans confirmation → bloqué (confirmation requise)", () => {
  const decision = authorizeSend(FAITHFUL);
  assert.equal(decision.authorized, false);
  assert.deepEqual(decision.reasons, [BLOCK_REASONS.CONFIRMATION]);
});

test("authorizeSend : candidature fidèle + confirmée → autorisé", () => {
  const decision = authorizeSend(FAITHFUL, CONFIRMED);
  assert.equal(decision.authorized, true);
  assert.deepEqual(decision.reasons, []);
});

test("authorizeSend : invention → bloqué même si confirmé", () => {
  const invented = {
    profile: PROFILE,
    coverLetter: { highlightedSkills: ["Kubernetes"] }, // non détenu
  };
  const decision = authorizeSend(invented, CONFIRMED);
  assert.equal(decision.authorized, false);
  assert.deepEqual(decision.reasons, [BLOCK_REASONS.INVENTION]);
});

test("authorizeSend : les deux barrières peuvent se cumuler", () => {
  const decision = authorizeSend({ profile: PROFILE, coverLetter: { highlightedSkills: ["Kubernetes"] } });
  assert.deepEqual(decision.reasons, [BLOCK_REASONS.INVENTION, BLOCK_REASONS.CONFIRMATION]);
});

test("authorizeSend : confirmation non stricte (truthy) refusée", () => {
  for (const value of ["true", 1, "yes", {}]) {
    assert.equal(authorizeSend(FAITHFUL, { confirmed: value }).authorized, false);
  }
});

// --- performSend ---

test("performSend : exécute l'envoi seulement si autorisé", () => {
  let sent = false;
  const result = performSend(FAITHFUL, CONFIRMED, () => {
    sent = true;
    return "envoyé";
  });
  assert.equal(sent, true);
  assert.equal(result, "envoyé");
});

test("performSend : bloqué sans confirmation → lève et n'appelle pas send", () => {
  let sent = false;
  assert.throws(
    () => performSend(FAITHFUL, {}, () => { sent = true; }),
    /Envoi bloqué.*confirmation_requise/,
  );
  assert.equal(sent, false);
});

test("performSend : autorisé mais fonction d'envoi manquante → erreur explicite", () => {
  assert.throws(() => performSend(FAITHFUL, CONFIRMED), /fonction d'envoi/);
});
