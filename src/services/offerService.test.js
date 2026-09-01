const { test } = require("node:test");
const assert = require("node:assert/strict");

const {
  validateOffer,
  createValidOffer,
  updateValidOffer,
} = require("./offerService");

// Offre minimale valide, réutilisée par plusieurs tests.
const validData = {
  title: "Développeur JS",
  company: "ACME",
  source: "LinkedIn",
  url: "https://example.com/offre",
  contractType: "CDI",
};

test("validateOffer : accepte une offre complète", () => {
  assert.equal(validateOffer(validData).valid, true);
});

test("validateOffer : refuse chaînes vides et contractType hors CDI/FREELANCE", () => {
  const result = validateOffer({
    title: "",
    company: "   ", // espaces seuls
    source: "",
    url: "",
    contractType: "freelance", // minuscule → invalide
  });

  assert.equal(result.valid, false);
  assert.equal(result.errors.length, 5);
});

test("createValidOffer : renvoie une offre valide avec un id", () => {
  const offer = createValidOffer(validData);
  assert.ok(offer.id);
  assert.equal(offer.contractType, "CDI");
});

test("createValidOffer : lève une erreur sur une offre invalide", () => {
  assert.throws(() => createValidOffer({}), /obligatoire|invalide/);
});

test("updateValidOffer : autorise la modification des champs optionnels", () => {
  const offer = createValidOffer(validData);
  const updated = updateValidOffer(offer, { compensation: "55k€", location: "Remote" });
  assert.equal(updated.compensation, "55k€");
  assert.equal(updated.location, "Remote");
});

test("updateValidOffer : lève une erreur si la mise à jour casse un champ obligatoire", () => {
  const offer = createValidOffer(validData);
  assert.throws(() => updateValidOffer(offer, { title: "" }), /obligatoire/);
});
