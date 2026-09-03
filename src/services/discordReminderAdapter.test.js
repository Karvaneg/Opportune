const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

const {
  listFollowUpsToNotify,
  buildFollowUpReminderMessage,
  remindDueFollowUps,
} = require("./discordReminderAdapter");
const { saveValidApplication } = require("./applicationService");

// Store temporaire isolé par test.
function tmpStore() {
  return path.join(os.tmpdir(), `reminder-apps-${process.hrtime.bigint()}.json`);
}

// Date de référence stable pour les tests.
const NOW = new Date("2026-09-03T00:00:00.000Z");

// Prépare un store peuplé de candidatures aux relances variées pour le profil p1.
function seededStore() {
  const store = tmpStore();
  saveValidApplication({ profileId: "p1", offerId: "o1", followUpAt: "2026-09-01", status: "À étudier" }, store); // échue
  saveValidApplication({ profileId: "p1", offerId: "o2", followUpAt: "2026-09-10", status: "Validée" }, store); // à venir
  saveValidApplication({ profileId: "p1", offerId: "o3", followUpAt: "2026-08-20", status: "Abandonnée" }, store); // close → exclue
  saveValidApplication({ profileId: "p1", offerId: "o4", followUpAt: null, status: "À étudier" }, store); // sans relance → exclue
  return store;
}

// --- Sélection des relances ---

test("listFollowUpsToNotify : horizon 0 → seulement les relances échues et non closes", () => {
  const store = seededStore();
  const due = listFollowUpsToNotify("p1", { now: NOW, filePath: store });
  assert.deepEqual(due.map((a) => a.offerId), ["o1"]);
});

test("listFollowUpsToNotify : l'horizon inclut les relances à venir, triées par date", () => {
  const store = seededStore();
  const due = listFollowUpsToNotify("p1", { now: NOW, horizonDays: 10, filePath: store });
  assert.deepEqual(due.map((a) => a.offerId), ["o1", "o2"]);
});

test("listFollowUpsToNotify : exclut les candidatures closes et sans date de relance", () => {
  const store = seededStore();
  const due = listFollowUpsToNotify("p1", { now: NOW, horizonDays: 60, filePath: store });
  const offers = due.map((a) => a.offerId);
  assert.ok(!offers.includes("o3")); // close
  assert.ok(!offers.includes("o4")); // sans relance
});

// --- Construction du message ---

test("buildFollowUpReminderMessage : un champ par relance, date et statut", () => {
  const message = buildFollowUpReminderMessage([
    { offerId: "o1", followUpAt: "2026-09-01", status: "À étudier" },
  ]);
  assert.equal(message.embeds.length, 1);
  assert.match(message.embeds[0].title, /1 relance\(s\)/);
  assert.equal(message.embeds[0].fields[0].name, "o1");
  assert.match(message.embeds[0].fields[0].value, /2026-09-01.*À étudier/);
});

test("buildFollowUpReminderMessage : resolveOffer donne un intitulé lisible", () => {
  const message = buildFollowUpReminderMessage(
    [{ offerId: "o1", followUpAt: "2026-09-01", status: "À étudier" }],
    { resolveOffer: (id) => (id === "o1" ? { title: "Dev Fullstack — Alma" } : null) },
  );
  assert.equal(message.embeds[0].fields[0].name, "Dev Fullstack — Alma");
});

// --- Envoi ---

test("remindDueFollowUps : envoie un rappel quand des relances sont dues", async () => {
  const store = seededStore();
  const sent = [];
  const result = await remindDueFollowUps("p1", { send: (m) => sent.push(m), now: NOW, filePath: store });

  assert.equal(result.count, 1);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].embeds[0].fields.length, 1);
});

test("remindDueFollowUps : aucune relance due → n'appelle pas send, message null", async () => {
  const store = seededStore();
  let called = false;
  // now antérieur à toutes les relances → rien à notifier.
  const result = await remindDueFollowUps("p1", {
    send: () => (called = true),
    now: new Date("2026-08-01T00:00:00.000Z"),
    filePath: store,
  });

  assert.equal(result.count, 0);
  assert.equal(result.message, null);
  assert.equal(called, false);
});

test("remindDueFollowUps : fonction d'envoi manquante → erreur explicite", async () => {
  await assert.rejects(() => remindDueFollowUps("p1", { filePath: tmpStore() }), /send/i);
});
