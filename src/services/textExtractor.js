// Extraction du texte d'un CV. Interface unique extractText(filePath).
// Supporte réellement TXT et MD ; PDF et DOCX sont reconnus mais refusés
// proprement (UnsupportedFormatError) tant qu'aucun extracteur binaire n'existe.
// L'ajout de PDF/DOCX (dépendances tierces) fera l'objet d'un ticket dédié.
const fs = require("node:fs");

const { SUPPORTED_FORMATS, formatFromPath } = require("../models/resume");

// Erreur explicite pour un format reconnu mais non extractible (PDF, DOCX)
// ou une extension inconnue.
class UnsupportedFormatError extends Error {
  constructor(format) {
    super(`Format non supporté pour l'extraction : ${format}`);
    this.name = "UnsupportedFormatError";
    this.format = format;
  }
}

// Extrait le contenu textuel du fichier. Lit le fichier en lecture seule :
// le contenu original n'est jamais modifié.
function extractText(filePath) {
  const format = formatFromPath(filePath);

  if (!SUPPORTED_FORMATS.includes(format)) {
    throw new UnsupportedFormatError(format ?? "inconnu");
  }

  try {
    return fs.readFileSync(filePath, "utf8");
  } catch (cause) {
    throw new Error(`Fichier CV illisible : ${filePath}`, { cause });
  }
}

module.exports = { UnsupportedFormatError, extractText };
