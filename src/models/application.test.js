const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  DEFAULT_STATUS,
  createApplication,
  updateApplication,
} = require("./application");

test("createApplication : valeurs par défaut et id généré", () => {
  const app = createApplication({ profileId: "p1", offerId: "o1" });
  assert.equal(app.profileId, "p1");
  assert.equal(app.offerId, "o1");
  assert.equal(app.status, DEFAULT_STATUS);
  assert.equal(app.score, null);
  assert.deepEqual(app.documents, []);
  assert.equal(app.appliedAt, null);
  assert.ok(app.id && app.createdAt && app.updatedAt);
});

test("createApplication : deux ids distincts, id fourni conservé", () => {
  assert.notEqual(createApplication().id, createApplication().id);
  assert.equal(createApplication({ id: "fixed" }).id, "fixed");
});

test("updateApplication : applique les changements, garde l'id, rafraîchit updatedAt", async () => {
  const app = createApplication({ profileId: "p1", offerId: "o1", createdAt: "2020-01-01T00:00:00.000Z", updatedAt: "2020-01-01T00:00:00.000Z" });
  await new Promise((r) => setTimeout(r, 2));
  const updated = updateApplication(app, { status: "envoyée", id: "hack" });
  assert.equal(updated.id, app.id); // id stable
  assert.equal(updated.status, "envoyée");
  assert.notEqual(updated.updatedAt, app.updatedAt);
});
