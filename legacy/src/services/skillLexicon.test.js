const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  SKILL_NAMES,
  findSkillsInText,
  canonicalizeSkillName,
} = require("./skillLexicon");

// --- findSkillsInText ---

test("findSkillsInText : détecte dans l'ordre du catalogue, sans doublon", () => {
  assert.deepEqual(findSkillsInText("Stack React, nodejs, TypeScript, PostgreSQL"), [
    "TypeScript",
    "Node.js",
    "React",
    "SQL",
  ]);
});

test("findSkillsInText : Notion/Render exigent la majuscule", () => {
  assert.deepEqual(findSkillsInText("Docs Notion, déployé sur Render"), ["Render", "Notion"]);
  assert.deepEqual(findSkillsInText("des notions de css et server-side render"), []);
});

test("findSkillsInText : texte vide ou non-string → []", () => {
  assert.deepEqual(findSkillsInText(""), []);
  assert.deepEqual(findSkillsInText(null), []);
});

// --- canonicalizeSkillName ---

test("canonicalizeSkillName : libellé de profil → nom canonique", () => {
  assert.equal(canonicalizeSkillName("PostgreSQL"), "SQL");
  assert.equal(canonicalizeSkillName("react.js"), "React");
  assert.equal(canonicalizeSkillName("Node.js"), "Node.js");
});

test("canonicalizeSkillName : inconnu ou vide → null", () => {
  assert.equal(canonicalizeSkillName("Rust"), null);
  assert.equal(canonicalizeSkillName(""), null);
  assert.equal(canonicalizeSkillName(undefined), null);
});

test("SKILL_NAMES : expose les noms canoniques du catalogue", () => {
  assert.ok(SKILL_NAMES.includes("Symfony"));
  assert.ok(SKILL_NAMES.includes("Supabase"));
  assert.ok(!SKILL_NAMES.includes("Rust"));
});
