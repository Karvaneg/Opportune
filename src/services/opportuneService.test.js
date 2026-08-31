const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  scoreTicket,
  recommendNextTicket,
  getUrgentTickets,
  suggestPriority,
} = require("./opportuneService");

// Raccourci pour fabriquer un ticket minimal.
const t = (priorite, statut, extra = {}) => ({ priorite, statut, ...extra });

test("scoreTicket : priorité + statut cumulés", () => {
  assert.equal(scoreTicket(t("P0", "Backlog")), 6); // 4 + 2
  assert.equal(scoreTicket(t("P1", "In Progress")), 4); // 3 + 1
  assert.equal(scoreTicket(t("P3", "Review")), 2); // 1 + 1
});

test("scoreTicket : P0 pèse plus que P3", () => {
  assert.ok(scoreTicket(t("P0", "Backlog")) > scoreTicket(t("P3", "Backlog")));
});

test("scoreTicket : non démarré (Backlog) pèse plus qu'en cours (In Progress)", () => {
  assert.ok(scoreTicket(t("P1", "Backlog")) > scoreTicket(t("P1", "In Progress")));
});

test("scoreTicket : valeurs inconnues ou nulles → 0", () => {
  assert.equal(scoreTicket(t(null, null)), 0);
  assert.equal(scoreTicket(t("P9", "Inconnu")), 0);
  assert.equal(scoreTicket({}), 0);
});

test("recommendNextTicket : renvoie le ticket au score le plus élevé", () => {
  const tickets = [
    t("P2", "Backlog", { id: "A" }), // 4
    t("P0", "Backlog", { id: "B" }), // 6
    t("P1", "In Progress", { id: "C" }), // 4
  ];
  const reco = recommendNextTicket(tickets);
  assert.equal(reco.id, "B");
  assert.equal(reco.score, 6);
});

test("recommendNextTicket : exclut les tickets terminés", () => {
  const tickets = [
    t("P0", "Done", { id: "termine" }), // exclu malgré P0
    t("P3", "Backlog", { id: "restant" }), // 2
  ];
  assert.equal(recommendNextTicket(tickets).id, "restant");
});

test("recommendNextTicket : enrichit le ticket d'un champ score sans muter l'original", () => {
  const original = t("P0", "Backlog", { id: "X" });
  const reco = recommendNextTicket([original]);
  assert.equal(reco.score, 6);
  assert.equal("score" in original, false);
});

test("recommendNextTicket : liste vide ou tout terminé → null", () => {
  assert.equal(recommendNextTicket([]), null);
  assert.equal(recommendNextTicket([t("P0", "Done")]), null);
});

test("getUrgentTickets : ne garde que les scores >= seuil, triés", () => {
  const tickets = [
    t("P0", "Backlog", { id: "A" }), // 6
    t("P2", "Backlog", { id: "B" }), // 4  -> exclu
    t("P1", "Backlog", { id: "C" }), // 5
  ];
  const urgents = getUrgentTickets(tickets);
  assert.deepEqual(urgents.map((u) => u.id), ["A", "C"]);
});

test("getUrgentTickets : exclut les tickets terminés même très prioritaires", () => {
  assert.deepEqual(getUrgentTickets([t("P0", "Done")]), []);
});

test("getUrgentTickets : seuil personnalisable", () => {
  const tickets = [t("P3", "In Progress", { id: "bas" })]; // score 2
  assert.equal(getUrgentTickets(tickets, 5).length, 0);
  assert.equal(getUrgentTickets(tickets, 2).length, 1);
});

test("suggestPriority : MVP + Bug → P0", () => {
  assert.equal(suggestPriority({ phase: "MVP", type: "Bug" }), "P0");
});

test("suggestPriority : MVP feature → P2, V1 bug → P1", () => {
  assert.equal(suggestPriority({ phase: "MVP", type: "Feature" }), "P2");
  assert.equal(suggestPriority({ phase: "V1", type: "Bug" }), "P1");
});

test("suggestPriority : aucun signal → P3", () => {
  assert.equal(suggestPriority({}), "P3");
  assert.equal(suggestPriority({ phase: "V2", type: "Feature" }), "P3");
});
