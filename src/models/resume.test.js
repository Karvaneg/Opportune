const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  createResume,
  updateResume,
  formatFromPath,
  toPublicView,
} = require("./resume");

test("formatFromPath : déduit le format depuis l'extension", () => {
  assert.equal(formatFromPath("cv.txt"), "TXT");
  assert.equal(formatFromPath("cv.MD"), "MD");
  assert.equal(formatFromPath("/tmp/cv.pdf"), "PDF");
  assert.equal(formatFromPath("cv.docx"), "DOCX");
  assert.equal(formatFromPath("cv.rtf"), null);
});

test("createResume : id généré, défauts neutres, importedAt daté", () => {
  const cv = createResume();
  assert.ok(cv.id);
  assert.equal(cv.isDefault, false);
  assert.equal(cv.archived, false);
  assert.equal(cv.extractedText, "");
  assert.ok(cv.importedAt); // horodaté
});

test("updateResume : applique les changements, préserve l'id, sans muter", () => {
  const cv = createResume({ id: "x", name: "A" });
  const updated = updateResume(cv, { name: "B", id: "hack", archived: true });
  assert.equal(updated.name, "B");
  assert.equal(updated.archived, true);
  assert.equal(updated.id, "x"); // id stable
  assert.equal(cv.name, "A"); // original intact
});

test("toPublicView : masque sourcePath", () => {
  const cv = createResume({ name: "CV", sourcePath: "/interne/cv.txt" });
  const pub = toPublicView(cv);
  assert.equal("sourcePath" in pub, false);
  assert.equal(pub.name, "CV");
});
