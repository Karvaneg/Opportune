const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  validateApplication,
  createValidApplication,
  saveValidApplication,
  listApplications,
  getApplication,
  updateApplicationById,
} = require("./applicationService");

function tmpFile() {
  return path.join(os.tmpdir(), `applications-svc-${process.hrtime.bigint()}.json`);
}

// --- validation ---

test("validateApplication : profil et offre obligatoires", () => {
  const result = validateApplication({ profileId: "", offerId: "" });
  assert.equal(result.valid, false);
  assert.equal(result.errors.length, 2);
});

test("validateApplication : score hors bornes refusé", () => {
  assert.equal(validateApplication({ profileId: "p", offerId: "o", score: 150 }).valid, false);
  assert.equal(validateApplication({ profileId: "p", offerId: "o", score: 80 }).valid, true);
  assert.equal(validateApplication({ profileId: "p", offerId: "o", score: null }).valid, true);
});

test("createValidApplication : lève si champ obligatoire manquant", () => {
  assert.throws(() => createValidApplication({ profileId: "p" }), /offre/i);
});

// --- persistance / CRUD ---

test("saveValidApplication + listApplications + getApplication", () => {
  const file = tmpFile();
  try {
    const a = saveValidApplication({ profileId: "p1", offerId: "o1", score: 87 }, file);
    saveValidApplication({ profileId: "p1", offerId: "o2" }, file);
    saveValidApplication({ profileId: "p2", offerId: "o3" }, file);

    assert.equal(listApplications("p1", file).length, 2);
    assert.equal(getApplication(a.id, file).score, 87);
    assert.equal(getApplication("inconnu", file), null);
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("updateApplicationById : modifie, revalide et persiste ; erreur si introuvable", () => {
  const file = tmpFile();
  try {
    const a = saveValidApplication({ profileId: "p1", offerId: "o1" }, file);

    const updated = updateApplicationById(a.id, { status: "envoyée", nextAction: "relancer sous 7j" }, file);
    assert.equal(updated.status, "envoyée");
    assert.equal(updated.nextAction, "relancer sous 7j");
    assert.equal(getApplication(a.id, file).status, "envoyée");

    assert.throws(() => updateApplicationById("inconnu", {}, file), /introuvable/i);
    // Une mise à jour qui casse un champ obligatoire est refusée
    assert.throws(() => updateApplicationById(a.id, { offerId: "" }, file), /offre/i);
  } finally {
    fs.rmSync(file, { force: true });
  }
});
