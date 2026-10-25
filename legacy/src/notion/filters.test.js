const { test } = require("node:test");
const assert = require("node:assert/strict");

const { buildFilter } = require("./filters");

test("sans argument → aucun filtre (undefined)", () => {
  assert.equal(buildFilter(), undefined);
  assert.equal(buildFilter({}), undefined);
});

test("un filtre statut → condition status equals", () => {
  assert.deepEqual(buildFilter({ statut: "Backlog" }), {
    and: [{ property: "Statut", status: { equals: "Backlog" } }],
  });
});

test("un filtre priorité → condition select equals", () => {
  assert.deepEqual(buildFilter({ priorite: "P0" }), {
    and: [{ property: "Priorité", select: { equals: "P0" } }],
  });
});

test("filtres combinés → and de plusieurs conditions", () => {
  const filtre = buildFilter({ statut: "Backlog", phase: "MVP" });
  assert.deepEqual(filtre.and, [
    { property: "Statut", status: { equals: "Backlog" } },
    { property: "Phase", select: { equals: "MVP" } },
  ]);
});

test("valeurs nulles ou indéfinies → ignorées", () => {
  assert.equal(buildFilter({ statut: null, priorite: undefined }), undefined);
});

test("clé inconnue → ignorée silencieusement", () => {
  assert.equal(buildFilter({ inconnu: "x" }), undefined);
});
