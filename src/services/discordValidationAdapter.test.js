const { test } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const os = require("node:os");

const {
  encodeCustomId,
  parseCustomId,
  buildDiscordValidationMessage,
  handleValidationInteraction,
  createValidationInteractionHandler,
  COMPONENT_TYPE,
  BUTTON_STYLE,
} = require("./discordValidationAdapter");
const { saveValidApplication, getApplication } = require("./applicationService");

// Store temporaire isolé par test.
function tmpStore() {
  return path.join(os.tmpdir(), `discord-apps-${process.hrtime.bigint()}.json`);
}

// Fausse interaction Discord (bouton), capturant les appels update/reply.
function fakeButtonInteraction(customId) {
  const calls = { update: [], reply: [] };
  return {
    customId,
    componentType: COMPONENT_TYPE.BUTTON,
    update: async (payload) => calls.update.push(payload),
    reply: async (payload) => calls.reply.push(payload),
    calls,
  };
}

// --- customId ---

test("encodeCustomId / parseCustomId : aller-retour fidèle", () => {
  const customId = encodeCustomId("app-123", "accept");
  assert.deepEqual(parseCustomId(customId), { applicationId: "app-123", decision: "accept" });
});

test("parseCustomId : robuste à un id contenant des séparateurs", () => {
  const uuid = "3d01ac04:a335:81f7"; // séparateurs internes
  assert.deepEqual(parseCustomId(encodeCustomId(uuid, "reject")), {
    applicationId: uuid,
    decision: "reject",
  });
});

test("parseCustomId : ignore un customId étranger ou une décision inconnue", () => {
  assert.equal(parseCustomId("autre:bouton:x"), null);
  assert.equal(parseCustomId("opp:review:app-1:teleporter"), null);
  assert.equal(parseCustomId(undefined), null);
});

// --- Construction du message ---

test("buildDiscordValidationMessage : embed + rangée de 3 boutons décisionnels", () => {
  const msg = buildDiscordValidationMessage("app-9", { title: "Dev", company: "Alma" }, {});

  assert.equal(msg.embeds.length, 1);
  const names = msg.embeds[0].fields.map((f) => f.name);
  assert.ok(names.includes("Score"));
  assert.ok(names.includes("Recommandation"));

  const row = msg.components[0];
  assert.equal(row.type, COMPONENT_TYPE.ACTION_ROW);
  assert.equal(row.components.length, 3);

  const decisions = row.components.map((b) => parseCustomId(b.custom_id).decision);
  assert.deepEqual(decisions, ["accept", "reject", "hold"]);
  const accept = row.components.find((b) => b.custom_id.endsWith(":accept"));
  assert.equal(accept.style, BUTTON_STYLE.SUCCESS);
});

// --- Gestion des interactions ---

test("handleValidationInteraction : accept → statut Validée et message mis à jour", async () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);

  const interaction = fakeButtonInteraction(encodeCustomId(app.id, "accept"));
  const result = await handleValidationInteraction(interaction, store);

  assert.equal(result.decision, "accept");
  assert.equal(result.application.status, "Validée");
  assert.equal(getApplication(app.id, store).status, "Validée");
  // Le message d'origine est mis à jour sans boutons.
  assert.equal(interaction.calls.update.length, 1);
  assert.deepEqual(interaction.calls.update[0].components, []);
});

test("handleValidationInteraction : reject → statut Abandonnée", async () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);

  const result = await handleValidationInteraction(fakeButtonInteraction(encodeCustomId(app.id, "reject")), store);
  assert.equal(result.application.status, "Abandonnée");
});

test("handleValidationInteraction : hold → candidature inchangée", async () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);

  const result = await handleValidationInteraction(fakeButtonInteraction(encodeCustomId(app.id, "hold")), store);
  assert.equal(result.application.status, "À étudier");
  assert.equal(getApplication(app.id, store).status, "À étudier");
});

test("handleValidationInteraction : interaction étrangère → null (ignorée)", async () => {
  const store = tmpStore();
  const foreign = fakeButtonInteraction("autre:systeme:42");
  assert.equal(await handleValidationInteraction(foreign, store), null);
  assert.equal(foreign.calls.update.length, 0);
});

test("handleValidationInteraction : non-bouton → null", async () => {
  assert.equal(await handleValidationInteraction({ customId: undefined }, tmpStore()), null);
});

test("handleValidationInteraction : candidature introuvable → erreur (réponse éphémère, pas de crash)", async () => {
  const interaction = fakeButtonInteraction(encodeCustomId("inexistant", "accept"));
  const result = await handleValidationInteraction(interaction, tmpStore());

  assert.equal(result.application, null);
  assert.match(result.error, /introuvable/i);
  assert.equal(interaction.calls.reply.length, 1);
  assert.equal(interaction.calls.reply[0].ephemeral, true);
});

test("createValidationInteractionHandler : prêt à brancher sur client.on(...)", async () => {
  const store = tmpStore();
  const app = saveValidApplication({ profileId: "p1", offerId: "o1" }, store);
  const handler = createValidationInteractionHandler(store);

  const result = await handler(fakeButtonInteraction(encodeCustomId(app.id, "accept")));
  assert.equal(result.application.status, "Validée");
});
