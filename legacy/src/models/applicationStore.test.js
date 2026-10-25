const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const { loadApplications, saveApplication, saveApplications } = require("./applicationStore");

// Chemin temporaire unique par test, nettoyé après.
function tmpFile() {
  return path.join(os.tmpdir(), `applications-${process.hrtime.bigint()}.json`);
}

test("loadApplications : retourne [] si le fichier n'existe pas", () => {
  assert.deepEqual(loadApplications(tmpFile()), []);
});

test("saveApplication : ajoute puis remplace via son id", () => {
  const file = tmpFile();
  try {
    saveApplication({ id: "a", status: "brouillon" }, file);
    saveApplication({ id: "b", status: "brouillon" }, file);
    assert.equal(loadApplications(file).length, 2);

    saveApplication({ id: "a", status: "envoyée" }, file); // remplace
    const apps = loadApplications(file);
    assert.equal(apps.length, 2);
    assert.equal(apps.find((a) => a.id === "a").status, "envoyée");
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("saveApplications : réécrit la collection entière", () => {
  const file = tmpFile();
  try {
    saveApplications([{ id: "a" }, { id: "b" }], file);
    assert.equal(loadApplications(file).length, 2);
    saveApplications([{ id: "c" }], file);
    assert.deepEqual(loadApplications(file).map((a) => a.id), ["c"]);
  } finally {
    fs.rmSync(file, { force: true });
  }
});
