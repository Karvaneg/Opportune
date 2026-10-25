const { test } = require("node:test");
const assert = require("node:assert/strict");

const { DEFAULT_THRESHOLDS, recommendAction, recommendForComparison } = require("./scoreRecommender");

test("recommendAction : seuils par défaut (postuler / à étudier / ignorer)", () => {
  assert.equal(recommendAction(80).action, "postuler");
  assert.equal(recommendAction(75).action, "postuler"); // borne incluse
  assert.equal(recommendAction(60).action, "a_etudier");
  assert.equal(recommendAction(50).action, "a_etudier"); // borne incluse
  assert.equal(recommendAction(40).action, "ignorer");
  assert.equal(recommendAction(0).action, "ignorer");
});

test("recommendAction : renvoie libellé et score", () => {
  const rec = recommendAction(90);
  assert.equal(rec.label, "Candidater");
  assert.equal(rec.score, 90);
});

test("recommendAction : seuils personnalisables", () => {
  assert.equal(recommendAction(65, { high: 60 }).action, "postuler");
  assert.equal(recommendAction(30, { medium: 20 }).action, "a_etudier");
});

test("recommendAction : score non numérique → erreur", () => {
  assert.throws(() => recommendAction("80"), /nombre/);
  assert.throws(() => recommendAction(NaN), /nombre/);
});

test("DEFAULT_THRESHOLDS : exposés et cohérents", () => {
  assert.ok(DEFAULT_THRESHOLDS.high > DEFAULT_THRESHOLDS.medium);
});

test("recommendForComparison : score d'un rapport → action", () => {
  const strong = {
    skills: { matched: ["React"], missing: [] },
    contractType: { compatible: true },
    salary: { status: "ok" },
    experience: { status: "ok" },
    location: { status: "match" },
    remote: { status: "match" },
    languages: { matched: ["anglais"], missing: [] },
  };
  assert.equal(recommendForComparison(strong).action, "postuler"); // score 100

  const weak = {
    skills: { matched: [], missing: ["React"] },
    contractType: { compatible: false },
  };
  assert.equal(recommendForComparison(weak).action, "ignorer"); // score 0
});
