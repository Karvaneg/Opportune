const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  validateResume,
  importResume,
  setDefaultResume,
} = require("./resumeService");
const { UnsupportedFormatError } = require("./textExtractor");

// Crée un .txt temporaire contenant du texte de CV.
function tmpCv(content = "Contenu du CV") {
  const file = path.join(os.tmpdir(), `cv-${process.hrtime.bigint()}.txt`);
  fs.writeFileSync(file, content);
  return file;
}

// Chemin temporaire unique pour la collection persistée.
function tmpStore() {
  return path.join(os.tmpdir(), `resumes-${process.hrtime.bigint()}.json`);
}

test("validateResume : rejette les métadonnées manquantes", () => {
  const result = validateResume({});
  assert.equal(result.valid, false);
  assert.ok(result.errors.length >= 3);
});

test("importResume : importe un .txt et extrait le texte", () => {
  const cvFile = tmpCv("Développeur Python");
  const store = tmpStore();
  try {
    const cv = importResume(
      { profileId: "p1", name: "CV — Python", sourcePath: cvFile },
      store,
    );
    assert.equal(cv.format, "TXT");
    assert.equal(cv.extractedText, "Développeur Python");
    assert.equal(cv.isDefault, true); // premier CV du profil
  } finally {
    fs.rmSync(cvFile, { force: true });
    fs.rmSync(store, { force: true });
  }
});

test("importResume : le 2e CV du profil n'est pas défaut automatiquement", () => {
  const a = tmpCv("A");
  const b = tmpCv("B");
  const store = tmpStore();
  try {
    const first = importResume({ profileId: "p1", name: "A", sourcePath: a }, store);
    const second = importResume({ profileId: "p1", name: "B", sourcePath: b }, store);
    assert.equal(first.isDefault, true);
    assert.equal(second.isDefault, false);
  } finally {
    [a, b, store].forEach((f) => fs.rmSync(f, { force: true }));
  }
});

test("importResume : PDF reconnu mais refusé (UnsupportedFormatError)", () => {
  const store = tmpStore();
  assert.throws(
    () => importResume({ profileId: "p1", name: "CV", sourcePath: "/tmp/cv.pdf" }, store),
    UnsupportedFormatError,
  );
});

test("importResume : import invalide (nom manquant) rejeté", () => {
  const cvFile = tmpCv();
  const store = tmpStore();
  try {
    assert.throws(
      () => importResume({ profileId: "p1", sourcePath: cvFile }, store),
      /nom/i,
    );
  } finally {
    fs.rmSync(cvFile, { force: true });
    fs.rmSync(store, { force: true });
  }
});

test("setDefaultResume : bascule le défaut, un seul défaut par profil", () => {
  const a = tmpCv("A");
  const b = tmpCv("B");
  const store = tmpStore();
  try {
    const first = importResume({ profileId: "p1", name: "A", sourcePath: a }, store);
    const second = importResume({ profileId: "p1", name: "B", sourcePath: b }, store);

    setDefaultResume("p1", second.id, store);

    const { loadResumes } = require("../models/resumeStore");
    const defaults = loadResumes(store).filter((r) => r.isDefault);
    assert.equal(defaults.length, 1);
    assert.equal(defaults[0].id, second.id);
  } finally {
    [a, b, store].forEach((f) => fs.rmSync(f, { force: true }));
  }
});
