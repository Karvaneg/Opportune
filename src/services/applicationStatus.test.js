const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  isValidStatus,
  nextStatuses,
  canTransition,
  isTerminal,
} = require("./applicationStatus");

test("isValidStatus : reconnaît l'échelle, rejette le reste", () => {
  assert.equal(isValidStatus("À étudier"), true);
  assert.equal(isValidStatus("Acceptée"), true);
  assert.equal(isValidStatus("brouillon"), false);
});

test("canTransition : suit le cycle de vie", () => {
  assert.equal(canTransition("À étudier", "Validée"), true);
  assert.equal(canTransition("Validée", "Envoyée"), true);
  assert.equal(canTransition("Envoyée", "Entretien"), true);
  assert.equal(canTransition("Entretien", "Acceptée"), true);
});

test("canTransition : refuse les sauts et retours en arrière", () => {
  assert.equal(canTransition("À étudier", "Envoyée"), false); // saute Validée
  assert.equal(canTransition("Entretien", "À étudier"), false); // retour arrière
  assert.equal(canTransition("Acceptée", "Entretien"), false); // depuis un état final
});

test("Abandonnée accessible depuis tout état non final", () => {
  for (const status of ["À étudier", "Validée", "Envoyée", "Entretien"]) {
    assert.equal(canTransition(status, "Abandonnée"), true);
  }
});

test("isTerminal : états finaux sans suite", () => {
  for (const status of ["Refusée", "Acceptée", "Abandonnée"]) {
    assert.equal(isTerminal(status), true);
    assert.deepEqual(nextStatuses(status), []);
  }
  assert.equal(isTerminal("Envoyée"), false);
});
