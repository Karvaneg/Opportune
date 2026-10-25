const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  OpportuneError,
  ValidationError,
  NotFoundError,
  InvalidTransitionError,
  ConfigError,
  SendBlockedError,
  normalizeError,
} = require("./index");

test("les erreurs typées héritent d'OpportuneError/Error et portent un code", () => {
  const cases = [
    [new ValidationError("x"), "VALIDATION", "ValidationError"],
    [new NotFoundError("x"), "NOT_FOUND", "NotFoundError"],
    [new InvalidTransitionError("x"), "INVALID_TRANSITION", "InvalidTransitionError"],
    [new ConfigError("x"), "CONFIG", "ConfigError"],
    [new SendBlockedError("x"), "SEND_BLOCKED", "SendBlockedError"],
  ];
  for (const [err, code, name] of cases) {
    assert.ok(err instanceof OpportuneError);
    assert.ok(err instanceof Error);
    assert.equal(err.code, code);
    assert.equal(err.name, name);
    assert.equal(err.operational, true);
  }
});

test("les détails sont attachés quand fournis", () => {
  const err = new SendBlockedError("Envoi bloqué", { reasons: ["confirmation_requise"] });
  assert.deepEqual(err.details, { reasons: ["confirmation_requise"] });
});

test("normalizeError : préserve code/message/details d'une OpportuneError", () => {
  const err = new ValidationError("Champ requis", { field: "offerId" });
  assert.deepEqual(normalizeError(err), {
    code: "VALIDATION",
    message: "Champ requis",
    operational: true,
    details: { field: "offerId" },
  });
});

test("normalizeError : masque les erreurs inattendues (pas de fuite de message)", () => {
  const leaked = new Error("chemin secret /home/user/.env exposé");
  const normalized = normalizeError(leaked);
  assert.equal(normalized.code, "INTERNAL");
  assert.equal(normalized.operational, false);
  assert.ok(!normalized.message.includes("secret"));
});

test("normalizeError : valeur non-Error → INTERNAL", () => {
  assert.equal(normalizeError("oops").code, "INTERNAL");
  assert.equal(normalizeError(undefined).operational, false);
});
