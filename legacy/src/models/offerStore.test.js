const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const { saveOffer, loadOffers } = require("./offerStore");

// Chemin temporaire unique par test, nettoyé après.
function tmpFile() {
  return path.join(os.tmpdir(), `offers-${process.hrtime.bigint()}.json`);
}

test("loadOffers : retourne [] si le fichier n'existe pas", () => {
  assert.deepEqual(loadOffers(tmpFile()), []);
});

test("saveOffer : ajoute puis remplace une offre via son id", () => {
  const file = tmpFile();
  try {
    saveOffer({ id: "a", title: "V1" }, file);
    saveOffer({ id: "b", title: "Autre" }, file);
    assert.equal(loadOffers(file).length, 2);

    saveOffer({ id: "a", title: "V2" }, file); // remplace, n'ajoute pas
    const offers = loadOffers(file);
    assert.equal(offers.length, 2);
    assert.equal(offers.find((o) => o.id === "a").title, "V2");
  } finally {
    fs.rmSync(file, { force: true });
  }
});
