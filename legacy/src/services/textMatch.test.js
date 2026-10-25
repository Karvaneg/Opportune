const { test } = require("node:test");
const assert = require("node:assert/strict");

const { containsTerm } = require("./textMatch");

test("containsTerm : terme entier, insensible à la casse par défaut", () => {
  assert.equal(containsTerm("Nous faisons du JavaScript", "javascript"), true);
  assert.equal(containsTerm("Aucune techno ici", "python"), false);
});

test("containsTerm : ne matche pas en sous-mot (java dans javascript)", () => {
  assert.equal(containsTerm("javascript", "java"), false);
});

test("containsTerm : gère la ponctuation (c++, c#, node.js)", () => {
  assert.equal(containsTerm("Expérience C++ requise", "c++"), true);
  assert.equal(containsTerm("Stack Node.js", "node.js"), true);
});

test("containsTerm : caseSensitive exige la casse exacte", () => {
  assert.equal(containsTerm("Docs sur Notion", "Notion", true), true);
  assert.equal(containsTerm("des notions de JS", "Notion", true), false);
});
