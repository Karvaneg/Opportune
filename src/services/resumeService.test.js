const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  validateResume,
  importResume,
  setDefaultResume,
  listResumes,
  getResume,
  replaceResume,
  archiveResume,
  deleteResume,
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

// Amorce une collection avec deux CV du profil "p1" (le 1er est défaut).
function seedTwo() {
  const a = tmpCv("A");
  const b = tmpCv("B");
  const store = tmpStore();
  const first = importResume({ profileId: "p1", name: "A", sourcePath: a }, store);
  const second = importResume({ profileId: "p1", name: "B", sourcePath: b }, store);
  return {
    store,
    first,
    second,
    cleanup: () => [a, b, store].forEach((f) => fs.rmSync(f, { force: true })),
  };
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

test("listResumes : exclut les archivés sauf includeArchived", () => {
  const s = seedTwo();
  try {
    archiveResume(s.second.id, {}, s.store); // second n'est pas défaut
    assert.equal(listResumes("p1", {}, s.store).length, 1);
    assert.equal(listResumes("p1", { includeArchived: true }, s.store).length, 2);
  } finally {
    s.cleanup();
  }
});

test("getResume : retourne le CV par id, ou null", () => {
  const s = seedTwo();
  try {
    assert.equal(getResume(s.first.id, s.store).name, "A");
    assert.equal(getResume("inexistant", s.store), null);
  } finally {
    s.cleanup();
  }
});

test("replaceResume : remplace le contenu en conservant id et statut de défaut", () => {
  const s = seedTwo();
  const newFile = tmpCv("Contenu remplacé");
  try {
    const updated = replaceResume(s.first.id, newFile, s.store);
    assert.equal(updated.id, s.first.id);
    assert.equal(updated.isDefault, true);
    assert.equal(updated.extractedText, "Contenu remplacé");
  } finally {
    s.cleanup();
    fs.rmSync(newFile, { force: true });
  }
});

test("archiveResume : archive un CV non-défaut, le défaut reste inchangé", () => {
  const s = seedTwo();
  try {
    const archived = archiveResume(s.second.id, {}, s.store);
    assert.equal(archived.archived, true);
    assert.equal(getResume(s.first.id, s.store).isDefault, true);
  } finally {
    s.cleanup();
  }
});

test("archiveResume : archiver le défaut sans remplaçant lève une erreur", () => {
  const s = seedTwo();
  try {
    assert.throws(
      () => archiveResume(s.first.id, {}, s.store),
      /nouveau CV par défaut/i,
    );
  } finally {
    s.cleanup();
  }
});

test("archiveResume : archiver le défaut en désignant le remplaçant", () => {
  const s = seedTwo();
  try {
    archiveResume(s.first.id, { newDefaultId: s.second.id }, s.store);
    assert.equal(getResume(s.first.id, s.store).archived, true);
    assert.equal(getResume(s.second.id, s.store).isDefault, true);
  } finally {
    s.cleanup();
  }
});

test("deleteResume : supprimer le défaut exige un remplaçant, puis le réassigne", () => {
  const s = seedTwo();
  try {
    assert.throws(() => deleteResume(s.first.id, {}, s.store), /nouveau CV par défaut/i);

    deleteResume(s.first.id, { newDefaultId: s.second.id }, s.store);
    assert.equal(getResume(s.first.id, s.store), null);
    assert.equal(getResume(s.second.id, s.store).isDefault, true);
  } finally {
    s.cleanup();
  }
});

test("deleteResume : supprimer le dernier CV actif (défaut) est permis", () => {
  const a = tmpCv("Seul");
  const store = tmpStore();
  try {
    const only = importResume({ profileId: "p1", name: "Seul", sourcePath: a }, store);
    assert.equal(only.isDefault, true);
    deleteResume(only.id, {}, store); // dernier actif → pas de réassignation requise
    assert.equal(getResume(only.id, store), null);
  } finally {
    [a, store].forEach((f) => fs.rmSync(f, { force: true }));
  }
});
