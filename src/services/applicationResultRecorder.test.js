const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

const {
  RESULT_OUTCOMES,
  isPositiveOutcome,
  recordResult,
  buildScoringFeedback,
  analyzeScoreCalibration,
} = require("./applicationResultRecorder");
const { saveValidApplication } = require("./applicationService");

// Chemin de store temporaire, isolé par test.
function tmpStore() {
  return path.join(os.tmpdir(), `applications-${process.hrtime.bigint()}.json`);
}

// --- isPositiveOutcome ---

test("isPositiveOutcome : accepted et interview sont positifs, pas rejected/no_response", () => {
  assert.equal(isPositiveOutcome("accepted"), true);
  assert.equal(isPositiveOutcome("interview"), true);
  assert.equal(isPositiveOutcome("rejected"), false);
  assert.equal(isPositiveOutcome("no_response"), false);
});

test("RESULT_OUTCOMES expose les issues attendues", () => {
  assert.deepEqual(RESULT_OUTCOMES, ["accepted", "interview", "rejected", "no_response"]);
});

// --- recordResult ---

test("recordResult : enregistre l'issue et capture un instantané du score", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1", score: 82 }, store);
  const updated = recordResult(app.id, { outcome: "accepted", respondedAt: "2026-06-10" }, store);

  assert.equal(updated.result.outcome, "accepted");
  assert.equal(updated.result.respondedAt, "2026-06-10");
  assert.equal(updated.result.score, 82); // instantané du score
  assert.equal(updated.result.note, null);
});

test("recordResult : date de réponse par défaut = aujourd'hui (YYYY-MM-DD)", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1", score: 50 }, store);
  const updated = recordResult(app.id, { outcome: "rejected" }, store);
  assert.match(updated.result.respondedAt, /^\d{4}-\d{2}-\d{2}$/);
});

test("recordResult : conserve une note libre", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1", score: 60 }, store);
  const updated = recordResult(app.id, { outcome: "interview", note: "entretien le 15" }, store);
  assert.equal(updated.result.note, "entretien le 15");
});

test("recordResult : score null si la candidature n'a pas de score", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  const updated = recordResult(app.id, { outcome: "no_response" }, store);
  assert.equal(updated.result.score, null);
});

test("recordResult : issue invalide → ValidationError", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  assert.throws(() => recordResult(app.id, { outcome: "peut-être" }, store), /invalide/i);
});

test("recordResult : date de réponse invalide → ValidationError", () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  assert.throws(
    () => recordResult(app.id, { outcome: "accepted", respondedAt: "hier" }, store),
    /invalide/i,
  );
});

test("recordResult : candidature introuvable → NotFoundError", () => {
  const store = tmpStore();
  assert.throws(() => recordResult("inconnu", { outcome: "accepted" }, store), /introuvable/i);
});

// --- buildScoringFeedback ---

test("buildScoringFeedback : associe score et issue, ignore les candidatures sans résultat", () => {
  const store = tmpStore();
  const a = saveValidApplication({ profileId: "p1", offerId: "o1", score: 90 }, store);
  const b = saveValidApplication({ profileId: "p1", offerId: "o2", score: 40 }, store);
  saveValidApplication({ profileId: "p1", offerId: "o3", score: 70 }, store); // sans résultat → ignorée
  saveValidApplication({ profileId: "p2", offerId: "o4", score: 80 }, store); // autre profil

  recordResult(a.id, { outcome: "accepted" }, store);
  recordResult(b.id, { outcome: "rejected" }, store);

  const feedback = buildScoringFeedback("p1", store);
  assert.equal(feedback.length, 2);
  const byOffer = Object.fromEntries(feedback.map((f) => [f.offerId, f]));
  assert.deepEqual(
    { score: byOffer.o1.score, positive: byOffer.o1.positive },
    { score: 90, positive: true },
  );
  assert.deepEqual(
    { score: byOffer.o2.score, positive: byOffer.o2.positive },
    { score: 40, positive: false },
  );
});

// --- analyzeScoreCalibration ---

test("analyzeScoreCalibration : score moyen des issues positives vs négatives", () => {
  const feedback = [
    { score: 90, positive: true },
    { score: 80, positive: true },
    { score: 40, positive: false },
    { score: 30, positive: false },
  ];
  const analysis = analyzeScoreCalibration(feedback);
  assert.deepEqual(analysis.positive, { count: 2, averageScore: 85 });
  assert.deepEqual(analysis.negative, { count: 2, averageScore: 35 });
});

test("analyzeScoreCalibration : moyenne null quand aucune donnée", () => {
  const analysis = analyzeScoreCalibration([]);
  assert.deepEqual(analysis.positive, { count: 0, averageScore: null });
  assert.deepEqual(analysis.negative, { count: 0, averageScore: null });
});
