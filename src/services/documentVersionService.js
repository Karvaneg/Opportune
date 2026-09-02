// Versionnage des documents générés (OPP-045). Critère : chaque version est
// conservée et associée à l'offre. À chaque (re)génération ou édition d'un
// document (CV adapté, lettre, message LinkedIn), on enregistre une nouvelle
// version numérotée sans jamais écraser les précédentes.
//
// Logique pure au-dessus du store JSON (documentVersionStore). La numérotation
// des versions est par (offre, type de document) : la première vaut 1, chaque
// ajout incrémente.
const { createDocumentVersion, DOCUMENT_TYPES } = require("../models/documentVersion");
const {
  DEFAULT_PATH,
  loadDocumentVersions,
  saveDocumentVersion,
} = require("../models/documentVersionStore");
const { ValidationError } = require("../errors");

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Contrôle qu'une cible (offre, type de document) est valide ; lève sinon.
function assertValidTarget(offerId, type) {
  if (!isNonEmptyString(offerId)) {
    throw new ValidationError("L'offre associée (offerId) est obligatoire");
  }
  if (!DOCUMENT_TYPES.includes(type)) {
    throw new ValidationError(
      `Type de document invalide : ${type} (attendu ${DOCUMENT_TYPES.join(", ")})`,
    );
  }
}

// Liste les versions d'une offre, éventuellement filtrées par type de document.
// Triées par type puis par numéro de version croissant.
function listVersions(offerId, type = null, filePath = DEFAULT_PATH) {
  return loadDocumentVersions(filePath)
    .filter((v) => v.offerId === offerId && (type === null || v.type === type))
    .sort((a, b) =>
      a.type === b.type ? a.version - b.version : String(a.type).localeCompare(String(b.type)),
    );
}

// Retourne la dernière version d'un document pour une offre, ou null si aucune.
function getLatestVersion(offerId, type, filePath = DEFAULT_PATH) {
  assertValidTarget(offerId, type);
  const versions = listVersions(offerId, type, filePath);
  return versions.length > 0 ? versions[versions.length - 1] : null;
}

// Retourne une version précise (numéro) d'un document pour une offre, ou null.
function getVersion(offerId, type, version, filePath = DEFAULT_PATH) {
  assertValidTarget(offerId, type);
  return listVersions(offerId, type, filePath).find((v) => v.version === version) ?? null;
}

// Enregistre une nouvelle version d'un document pour une offre. Le numéro de
// version est calculé automatiquement (dernier + 1, ou 1). Les versions
// existantes sont conservées. Retourne la version enregistrée.
function addVersion({ offerId, type, content, label } = {}, filePath = DEFAULT_PATH) {
  assertValidTarget(offerId, type);
  if (content === undefined || content === null) {
    throw new ValidationError("Le contenu du document est obligatoire");
  }

  const latest = getLatestVersion(offerId, type, filePath);
  const version = latest ? latest.version + 1 : 1;

  const documentVersion = createDocumentVersion({ offerId, type, content, label, version });
  return saveDocumentVersion(documentVersion, filePath);
}

module.exports = {
  addVersion,
  listVersions,
  getLatestVersion,
  getVersion,
};
