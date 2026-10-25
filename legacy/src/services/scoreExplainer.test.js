const { test } = require("node:test");
const assert = require("node:assert/strict");

const { explainScore } = require("./scoreExplainer");

const COMPARISON = {
  skills: { matched: ["React", "SQL"], missing: ["TypeScript"] },
  contractType: { offer: "CDI", profile: "les deux", compatible: true },
  experience: { required: 4, profile: 6, status: "ok" },
  location: { offer: "Paris", profile: "Paris", status: "match", reason: null },
  remote: { offer: "hybrid", profile: "hybrid", status: "match" },
  languages: { matched: ["anglais"], missing: ["allemand"] },
  salary: { offer: { min: 45000, max: 60000, period: "year" }, target: 55000, status: "ok" },
};

test("explainScore : sépare raisons positives et négatives", () => {
  const { positives, negatives } = explainScore(COMPARISON);

  const posDims = positives.map((r) => r.dimension);
  assert.ok(posDims.includes("skills") && posDims.includes("contractType") && posDims.includes("salary"));
  assert.ok(positives.some((r) => /React, SQL/.test(r.message)));

  const negMessages = negatives.map((r) => r.message).join(" | ");
  assert.match(negMessages, /TypeScript/); // compétence manquante
  assert.match(negMessages, /allemand/); // langue manquante
});

test("explainScore : raisons triées par poids décroissant", () => {
  const { positives } = explainScore(COMPARISON);
  // skills (0.35) est la plus lourde → en tête des positives
  assert.equal(positives[0].dimension, "skills");
  for (let i = 1; i < positives.length; i++) {
    assert.ok(positives[i - 1].weight >= positives[i].weight);
  }
});

test("explainScore : expose le score et distingue insuffisance d'expérience", () => {
  const { score, negatives } = explainScore({
    ...COMPARISON,
    experience: { required: 5, profile: 2, status: "insufficient" },
  });
  assert.ok(typeof score === "number" && score >= 0 && score <= 100);
  assert.ok(negatives.some((r) => r.dimension === "experience" && /insuffisante/.test(r.message)));
});

test("explainScore : lieu non bloquant est une raison positive explicite", () => {
  const { positives } = explainScore({
    location: { offer: "Paris", profile: "Lyon", status: "not_blocking", reason: "offer-remote" },
  });
  assert.ok(positives.some((r) => r.dimension === "location" && /télétravail total/.test(r.message)));
});

test("explainScore : rapport vide → aucune raison positive/négative, dimensions inconnues remontées", () => {
  const { positives, negatives, unknown } = explainScore({});
  assert.deepEqual(positives, []);
  assert.deepEqual(negatives, []);
  assert.ok(unknown.length > 0);
});
