const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createSkill, updateSkill, SKILL_LEVELS } = require("./skill");

test("createSkill : défauts (niveau notion, catégorie null, sans expérience)", () => {
  const s = createSkill({ name: "JavaScript" });
  assert.equal(s.name, "JavaScript");
  assert.equal(s.category, null);
  assert.equal(s.level, "notion");
  assert.equal(s.experienceYears, undefined);
  assert.ok(SKILL_LEVELS.includes(s.level));
});

test("createSkill : conserve les valeurs fournies", () => {
  const s = createSkill({
    name: "Node.js",
    category: "runtime",
    level: "avancé",
    experienceYears: 4,
  });
  assert.equal(s.category, "runtime");
  assert.equal(s.level, "avancé");
  assert.equal(s.experienceYears, 4);
});

test("updateSkill : applique les changements sans muter l'original", () => {
  const s = createSkill({ name: "Python", level: "notion" });
  const updated = updateSkill(s, { level: "expert" });
  assert.equal(updated.level, "expert");
  assert.equal(s.level, "notion"); // original intact
});
