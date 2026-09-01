const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const {
  parseOfferText,
  draftOfferFromUrl,
  draftOfferFromText,
  confirmOffer,
} = require("./offerImportService");
const { loadOffers } = require("../models/offerStore");

function tmpStore() {
  return path.join(os.tmpdir(), `offers-${process.hrtime.bigint()}.json`);
}

// --- parseOfferText ---

test("parseOfferText : extrait les champs clé: valeur et normalise le contrat", () => {
  const fields = parseOfferText(
    "Titre: Développeur JS\nEntreprise: ACME\nContrat: freelance\nSalaire: 500€/j",
  );
  assert.equal(fields.title, "Développeur JS");
  assert.equal(fields.company, "ACME");
  assert.equal(fields.contractType, "FREELANCE"); // normalisé en majuscules
  assert.equal(fields.compensation, "500€/j");
});

test("parseOfferText : ignore les lignes sans séparateur", () => {
  assert.deepEqual(parseOfferText("juste du texte sans structure"), {});
});

// --- draftOfferFromUrl ---

test("draftOfferFromUrl : conserve l'URL et la source, brouillon non validé", () => {
  const draft = draftOfferFromUrl("https://example.com/offre");
  assert.equal(draft.url, "https://example.com/offre");
  assert.equal(draft.source, "manuel");
  assert.ok(draft.id);
  assert.ok(draft.importedAt); // date d'import présente
  assert.equal(draft.title, ""); // incomplet : pas d'erreur à ce stade
});

test("draftOfferFromUrl : les overrides complètent le brouillon", () => {
  const draft = draftOfferFromUrl("https://x", { title: "Dev", source: "discord" });
  assert.equal(draft.title, "Dev");
  assert.equal(draft.source, "discord");
  assert.equal(draft.url, "https://x"); // l'URL du paramètre prime
});

// --- draftOfferFromText ---

test("draftOfferFromText : pré-remplit depuis le texte, texte brut en description à défaut", () => {
  const draft = draftOfferFromText("Titre: Dev\nEntreprise: ACME");
  assert.equal(draft.title, "Dev");
  assert.equal(draft.company, "ACME");
  assert.match(draft.description, /Titre: Dev/); // texte conservé faute de description
});

test("draftOfferFromText : les overrides priment sur le texte", () => {
  const draft = draftOfferFromText("Titre: Ancien", { title: "Corrigé" });
  assert.equal(draft.title, "Corrigé");
});

// --- confirmOffer ---

test("confirmOffer : valide et enregistre un brouillon complété", () => {
  const store = tmpStore();
  try {
    const draft = draftOfferFromUrl("https://example.com/o", {
      title: "Dev JS",
      company: "ACME",
      source: "discord",
      contractType: "CDI",
    });
    const saved = confirmOffer(draft, store);

    const offers = loadOffers(store);
    assert.equal(offers.length, 1);
    assert.equal(offers[0].id, saved.id);
    assert.equal(offers[0].source, "discord");
    assert.ok(offers[0].importedAt);
  } finally {
    fs.rmSync(store, { force: true });
  }
});

test("confirmOffer : refuse un brouillon incomplet (rien n'est enregistré)", () => {
  const store = tmpStore();
  try {
    const draft = draftOfferFromUrl("https://example.com/o"); // titre/company/contrat manquants
    assert.throws(() => confirmOffer(draft, store), /obligatoire|invalide/);
    assert.deepEqual(loadOffers(store), []); // aucune persistance
  } finally {
    fs.rmSync(store, { force: true });
  }
});
