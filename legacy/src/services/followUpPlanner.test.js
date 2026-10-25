const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

const {
  DEFAULT_FOLLOW_UP_DELAY_DAYS,
  computeFollowUpDate,
  planFollowUp,
  clearFollowUp,
  isFollowUpDue,
  listDueFollowUps,
} = require("./followUpPlanner");
const { saveValidApplication } = require("./applicationService");

// Chemin de store temporaire, isolé par test.
function tmpStore() {
  return path.join(os.tmpdir(), `applications-${process.hrtime.bigint()}.json`);
}

// --- computeFollowUpDate (automatique) ---

test("computeFollowUpDate : base = date d'envoi + délai par défaut", () => {
  const date = computeFollowUpDate({ appliedAt: "2026-01-01" });
  assert.equal(date, "2026-01-08"); // +7 jours
});

test("computeFollowUpDate : délai personnalisé", () => {
  assert.equal(computeFollowUpDate({ appliedAt: "2026-01-01" }, { delayDays: 3 }), "2026-01-04");
});

test("computeFollowUpDate : à défaut d'envoi, base sur la date de création", () => {
  const date = computeFollowUpDate({ createdAt: "2026-02-10T09:00:00.000Z" }, { delayDays: 5 });
  assert.equal(date, "2026-02-15");
});

test("computeFollowUpDate : options.from prime sur la candidature", () => {
  assert.equal(
    computeFollowUpDate({ appliedAt: "2026-01-01" }, { from: "2026-03-01", delayDays: 1 }),
    "2026-03-02",
  );
});

test("computeFollowUpDate : délai négatif → ValidationError", () => {
  assert.throws(() => computeFollowUpDate({ appliedAt: "2026-01-01" }, { delayDays: -1 }), /délai/i);
});

test("DEFAULT_FOLLOW_UP_DELAY_DAYS vaut 7", () => {
  assert.equal(DEFAULT_FOLLOW_UP_DELAY_DAYS, 7);
});

// --- planFollowUp ---

test("planFollowUp : date manuelle posée telle quelle", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  const updated = planFollowUp(app.id, { date: "2026-05-20" }, store);
  assert.equal(updated.followUpAt, "2026-05-20");
});

test("planFollowUp : sans date, calcul automatique depuis la candidature", () => {
  const store = tmpStore();
  const app = saveValidApplication(
    { profileId: "p1", offerId: "o1", appliedAt: "2026-01-01" },
    store,
  );
  const updated = planFollowUp(app.id, {}, store);
  assert.equal(updated.followUpAt, "2026-01-08");
});

test("planFollowUp : date manuelle invalide → ValidationError", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  assert.throws(() => planFollowUp(app.id, { date: "pas une date" }, store), /invalide/i);
});

test("planFollowUp : candidature introuvable → NotFoundError", () => {
  const store = tmpStore();
  assert.throws(() => planFollowUp("inconnu", { date: "2026-05-20" }, store), /introuvable/i);
});

test("clearFollowUp : réinitialise la date de relance à null", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  planFollowUp(app.id, { date: "2026-05-20" }, store);
  const cleared = clearFollowUp(app.id, store);
  assert.equal(cleared.followUpAt, null);
});

// --- isFollowUpDue / listDueFollowUps ---

test("isFollowUpDue : due quand la date est atteinte et le statut non final", () => {
  const now = new Date("2026-06-01T00:00:00.000Z");
  assert.equal(isFollowUpDue({ followUpAt: "2026-05-30", status: "Envoyée" }, now), true);
  assert.equal(isFollowUpDue({ followUpAt: "2026-06-15", status: "Envoyée" }, now), false); // future
});

test("isFollowUpDue : jamais due sans date de relance", () => {
  assert.equal(isFollowUpDue({ followUpAt: null, status: "Envoyée" }), false);
});

test("isFollowUpDue : jamais due si la candidature est dans un état final", () => {
  const now = new Date("2026-06-01T00:00:00.000Z");
  assert.equal(isFollowUpDue({ followUpAt: "2026-05-30", status: "Refusée" }, now), false);
});

test("listDueFollowUps : ne renvoie que les relances dues d'un profil", () => {
  const store = tmpStore();
  const due = saveValidApplication(
    { profileId: "p1", offerId: "o1", status: "Envoyée", followUpAt: "2026-05-30" },
    store,
  );
  saveValidApplication(
    { profileId: "p1", offerId: "o2", status: "Envoyée", followUpAt: "2026-12-31" },
    store,
  ); // future
  saveValidApplication({ profileId: "p2", offerId: "o3", followUpAt: "2026-05-30" }, store); // autre profil

  const now = new Date("2026-06-01T00:00:00.000Z");
  const result = listDueFollowUps("p1", now, store);
  assert.equal(result.length, 1);
  assert.equal(result[0].id, due.id);
});
