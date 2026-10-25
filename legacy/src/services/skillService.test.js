const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  validateSkill,
  extractSkillsFromText,
  attachSkillsToProfile,
} = require("./skillService");
const { createSkill } = require("../models/skill");
const { createProfile } = require("../models/userProfile");

// --- validateSkill ---

test("validateSkill : accepte une compétence valide", () => {
  assert.equal(validateSkill(createSkill({ name: "JS", experienceYears: 0 })).valid, true);
});

test("validateSkill : refuse nom manquant, niveau invalide, expérience négative", () => {
  const r = validateSkill({ name: "", level: "guru", experienceYears: -2 });
  assert.equal(r.valid, false);
  assert.equal(r.errors.length, 3);
});

test("validateSkill : experienceYears non numérique refusée", () => {
  const r = validateSkill(createSkill({ name: "JS", experienceYears: "trois" }));
  assert.equal(r.valid, false);
});

// --- extractSkillsFromText ---

const LEXIQUE = ["JavaScript", "Node.js", "Python", "Java", "React"];

test("extractSkillsFromText : détecte les compétences du lexique (termes entiers)", () => {
  const skills = extractSkillsFromText("Développeur JavaScript et Node.js", LEXIQUE);
  const names = skills.map((s) => s.name);
  assert.deepEqual(names.sort(), ["JavaScript", "Node.js"]);
  assert.equal(skills[0].level, "notion");
});

test("extractSkillsFromText : ne matche pas Java à l'intérieur de JavaScript", () => {
  const skills = extractSkillsFromText("Je code en JavaScript", LEXIQUE);
  const names = skills.map((s) => s.name);
  assert.equal(names.includes("Java"), false);
  assert.equal(names.includes("JavaScript"), true);
});

test("extractSkillsFromText : insensible à la casse, conserve le nom du lexique, dédup", () => {
  const skills = extractSkillsFromText("react REACT reAct", ["React"]);
  assert.equal(skills.length, 1);
  assert.equal(skills[0].name, "React"); // nom du lexique conservé
});

test("extractSkillsFromText : texte vide → []", () => {
  assert.deepEqual(extractSkillsFromText("", LEXIQUE), []);
});

// --- attachSkillsToProfile ---

test("attachSkillsToProfile : mode obligatoire", () => {
  const p = createProfile({ name: "Alex" });
  assert.throws(() => attachSkillsToProfile(p, [createSkill({ name: "JS" })]), /mode requise/);
});

test("attachSkillsToProfile : replace remplit structuredSkills sans toucher skills (legacy)", () => {
  const p = createProfile({ name: "Alex", skills: ["JavaScript"] });
  const updated = attachSkillsToProfile(p, [createSkill({ name: "JS" })], { mode: "replace" });
  assert.deepEqual(updated.skills, ["JavaScript"]); // legacy intact
  assert.equal(updated.structuredSkills.length, 1);
  assert.equal(updated.structuredSkills[0].name, "JS");
  assert.deepEqual(p.structuredSkills, []); // original non muté
});

test("attachSkillsToProfile : merge fusionne en dédupliquant par nom", () => {
  let p = createProfile({ name: "Alex" });
  p = attachSkillsToProfile(p, [createSkill({ name: "JS" })], { mode: "replace" });
  p = attachSkillsToProfile(
    p,
    [createSkill({ name: "js" }), createSkill({ name: "Python" })],
    { mode: "merge" },
  );
  const names = p.structuredSkills.map((s) => s.name);
  assert.deepEqual(names, ["JS", "Python"]); // "js" dédupliqué avec "JS"
});

test("attachSkillsToProfile : rejette une compétence invalide", () => {
  const p = createProfile({ name: "Alex" });
  assert.throws(
    () => attachSkillsToProfile(p, [{ name: "", level: "notion" }], { mode: "replace" }),
    /obligatoire/,
  );
});
