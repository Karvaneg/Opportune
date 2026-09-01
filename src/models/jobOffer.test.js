const { test } = require("node:test");
const assert = require("node:assert/strict");

const { createOffer, updateOffer, OFFER_CONTRACT_TYPES } = require("./jobOffer");

test("createOffer : génère un id et des défauts neutres", () => {
  const o = createOffer();
  assert.ok(o.id); // id généré
  assert.equal(o.title, "");
  assert.equal(o.contractType, null);
  assert.equal(o.location, null);
});

test("createOffer : conserve les valeurs fournies, y compris un id", () => {
  const o = createOffer({ id: "x", title: "Dev", contractType: "CDI" });
  assert.equal(o.id, "x");
  assert.equal(o.title, "Dev");
  assert.ok(OFFER_CONTRACT_TYPES.includes(o.contractType));
});

test("updateOffer : applique les changements, préserve l'id, sans muter l'original", () => {
  const o = createOffer({ id: "x", title: "A" });
  const updated = updateOffer(o, { title: "B", id: "hack", location: "Paris" });
  assert.equal(updated.title, "B");
  assert.equal(updated.location, "Paris");
  assert.equal(updated.id, "x"); // id stable malgré la tentative
  assert.equal(o.title, "A"); // original intact
});
