const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  addVersion,
  listVersions,
  getLatestVersion,
  getVersion,
} = require("./documentVersionService");

// Chemin de store temporaire, isolé par test.
function tmpStore() {
  return path.join(os.tmpdir(), `doc-versions-${process.hrtime.bigint()}.json`);
}

// --- addVersion : numérotation et conservation ---

test("addVersion : première version d'un document commence à 1", () => {
  const store = tmpStore();
  const v = addVersion({ offerId: "offer-1", type: "cv", content: { skills: ["React"] } }, store);
  assert.equal(v.version, 1);
  assert.equal(v.offerId, "offer-1"); // associée à l'offre (critère)
  assert.equal(v.type, "cv");
  assert.ok(v.id && v.createdAt);
});

test("addVersion : chaque ajout incrémente et conserve les précédentes", () => {
  const store = tmpStore();
  addVersion({ offerId: "offer-1", type: "coverLetter", content: "v1" }, store);
  addVersion({ offerId: "offer-1", type: "coverLetter", content: "v2" }, store);
  const v3 = addVersion({ offerId: "offer-1", type: "coverLetter", content: "v3" }, store);

  assert.equal(v3.version, 3);
  const versions = listVersions("offer-1", "coverLetter", store);
  assert.equal(versions.length, 3); // toutes conservées, rien d'écrasé
  assert.deepEqual(versions.map((v) => v.content), ["v1", "v2", "v3"]);
});

test("addVersion : la numérotation est indépendante par offre et par type", () => {
  const store = tmpStore();
  addVersion({ offerId: "offer-1", type: "cv", content: "a" }, store);
  addVersion({ offerId: "offer-1", type: "coverLetter", content: "b" }, store);
  const cvV2 = addVersion({ offerId: "offer-1", type: "cv", content: "c" }, store);
  const otherOffer = addVersion({ offerId: "offer-2", type: "cv", content: "d" }, store);

  assert.equal(cvV2.version, 2); // 2e CV de offer-1
  assert.equal(otherOffer.version, 1); // 1er CV de offer-2, indépendant
});

test("addVersion : persiste sur disque (conservation entre appels)", () => {
  const store = tmpStore();
  addVersion({ offerId: "offer-1", type: "linkedInMessage", content: "x" }, store);
  assert.ok(fs.existsSync(store));
  // Nouvelle lecture indépendante
  assert.equal(listVersions("offer-1", "linkedInMessage", store).length, 1);
});

test("addVersion : accepte un libellé optionnel", () => {
  const store = tmpStore();
  const v = addVersion(
    { offerId: "offer-1", type: "cv", content: "x", label: "après relecture" },
    store,
  );
  assert.equal(v.label, "après relecture");
});

// --- Validation ---

test("addVersion : offerId manquant → ValidationError", () => {
  const store = tmpStore();
  assert.throws(() => addVersion({ type: "cv", content: "x" }, store), /offerId|offre/i);
});

test("addVersion : type invalide → ValidationError", () => {
  const store = tmpStore();
  assert.throws(
    () => addVersion({ offerId: "offer-1", type: "podcast", content: "x" }, store),
    /invalide/i,
  );
});

test("addVersion : contenu manquant → ValidationError", () => {
  const store = tmpStore();
  assert.throws(() => addVersion({ offerId: "offer-1", type: "cv" }, store), /contenu/i);
});

// --- Consultation ---

test("getLatestVersion : renvoie la dernière version, null si aucune", () => {
  const store = tmpStore();
  assert.equal(getLatestVersion("offer-1", "cv", store), null);
  addVersion({ offerId: "offer-1", type: "cv", content: "v1" }, store);
  addVersion({ offerId: "offer-1", type: "cv", content: "v2" }, store);
  assert.equal(getLatestVersion("offer-1", "cv", store).content, "v2");
});

test("getVersion : renvoie une version précise, null si absente", () => {
  const store = tmpStore();
  addVersion({ offerId: "offer-1", type: "cv", content: "v1" }, store);
  addVersion({ offerId: "offer-1", type: "cv", content: "v2" }, store);
  assert.equal(getVersion("offer-1", "cv", 1, store).content, "v1");
  assert.equal(getVersion("offer-1", "cv", 99, store), null);
});

test("listVersions : toutes les versions d'une offre, tous types confondus", () => {
  const store = tmpStore();
  addVersion({ offerId: "offer-1", type: "cv", content: "a" }, store);
  addVersion({ offerId: "offer-1", type: "coverLetter", content: "b" }, store);
  addVersion({ offerId: "offer-2", type: "cv", content: "c" }, store);

  const all = listVersions("offer-1", null, store);
  assert.equal(all.length, 2); // seulement offer-1
  assert.ok(all.every((v) => v.offerId === "offer-1"));
});
