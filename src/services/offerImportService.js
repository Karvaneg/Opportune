// Import manuel d'une offre, depuis une URL ou un texte collé (Discord, formulaire).
// Périmètre MVP : aucun fetch réseau ni parsing HTML (hors contrainte zéro-dépendance).
// Depuis une URL, on conserve l'URL et l'utilisateur complète les champs ; depuis un
// texte, extraction best-effort par lignes « clé: valeur ». Le brouillon est éditable
// et n'est validé/persisté qu'à la confirmation.
const { createOffer } = require("../models/jobOffer");
const { DEFAULT_PATH, saveOffer } = require("../models/offerStore");
const { validateOffer } = require("./offerService");

// Libellés reconnus dans un texte collé → champs de l'offre.
const FIELD_LABELS = {
  titre: "title",
  poste: "title",
  intitulé: "title",
  intitule: "title",
  entreprise: "company",
  société: "company",
  societe: "company",
  client: "company",
  source: "source",
  url: "url",
  lien: "url",
  localisation: "location",
  lieu: "location",
  ville: "location",
  contrat: "contractType",
  "type de contrat": "contractType",
  salaire: "compensation",
  rémunération: "compensation",
  remuneration: "compensation",
  budget: "compensation",
  tjm: "compensation",
  description: "description",
  date: "publishedAt",
  "date de publication": "publishedAt",
  "publié le": "publishedAt",
};

// Normalise un type de contrat vers CDI / FREELANCE si reconnu, sinon inchangé
// (la valeur non reconnue sera rejetée à la validation).
function normalizeContractType(value) {
  const up = value.trim().toUpperCase();
  return up === "CDI" || up === "FREELANCE" ? up : value;
}

// Extrait des champs d'offre d'un texte, ligne à ligne au format « clé: valeur ».
function parseOfferText(text) {
  const fields = {};
  if (typeof text !== "string") return fields;

  for (const line of text.split(/\r?\n/)) {
    const sep = line.indexOf(":");
    if (sep < 0) continue;

    const label = line.slice(0, sep).trim().toLowerCase();
    const value = line.slice(sep + 1).trim();
    const key = FIELD_LABELS[label];
    if (!key || value === "") continue;

    fields[key] = key === "contractType" ? normalizeContractType(value) : value;
  }
  return fields;
}

// Construit un brouillon d'offre depuis une URL (conservée), source « manuel » par
// défaut. Non validé, non persisté : l'utilisateur complète puis confirme.
function draftOfferFromUrl(url, overrides = {}) {
  return createOffer({ source: "manuel", ...overrides, url });
}

// Construit un brouillon d'offre depuis un texte collé (extraction clé: valeur).
// À défaut de description explicite, le texte brut est conservé en description.
// Non validé, non persisté.
function draftOfferFromText(text, overrides = {}) {
  const parsed = parseOfferText(text);
  if (!parsed.description && typeof text === "string" && text.trim() !== "") {
    parsed.description = text.trim();
  }
  return createOffer({ source: "manuel", ...parsed, ...overrides });
}

// Valide puis enregistre un brouillon corrigé. Lève une erreur si l'offre est
// invalide (champs obligatoires manquants). Retourne l'offre enregistrée.
function confirmOffer(draft, filePath = DEFAULT_PATH) {
  const validation = validateOffer(draft);
  if (!validation.valid) {
    throw new Error(validation.errors.join(", "));
  }
  return saveOffer(draft, filePath);
}

module.exports = {
  parseOfferText,
  draftOfferFromUrl,
  draftOfferFromText,
  confirmOffer,
};
