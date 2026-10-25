const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const { extractText, UnsupportedFormatError } = require("./textExtractor");

// Écrit un fichier temporaire et renvoie son chemin.
function tmpFile(ext, content) {
  const file = path.join(os.tmpdir(), `cv-${process.hrtime.bigint()}${ext}`);
  fs.writeFileSync(file, content);
  return file;
}

test("extractText : lit le contenu d'un .txt", () => {
  const file = tmpFile(".txt", "Développeur JavaScript");
  try {
    assert.equal(extractText(file), "Développeur JavaScript");
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("extractText : lit le contenu d'un .md", () => {
  const file = tmpFile(".md", "# CV\nAutomatisation IA");
  try {
    assert.match(extractText(file), /Automatisation IA/);
  } finally {
    fs.rmSync(file, { force: true });
  }
});

test("extractText : refuse PDF avec UnsupportedFormatError", () => {
  assert.throws(() => extractText("/tmp/cv.pdf"), UnsupportedFormatError);
});

test("extractText : refuse DOCX avec UnsupportedFormatError", () => {
  assert.throws(() => extractText("/tmp/cv.docx"), UnsupportedFormatError);
});

test("extractText : extension inconnue → UnsupportedFormatError", () => {
  assert.throws(() => extractText("/tmp/cv.rtf"), UnsupportedFormatError);
});

test("extractText : fichier supporté mais illisible → erreur explicite", () => {
  assert.throws(
    () => extractText("/tmp/inexistant-cv.txt"),
    /illisible/,
  );
});
