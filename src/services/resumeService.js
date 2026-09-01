// Import et validation des CV d'un profil candidat.
const {
  RESUME_FORMATS,
  formatFromPath,
  createResume,
} = require("../models/resume");
const {
  DEFAULT_PATH,
  loadResumes,
  saveResume,
  saveResumes,
} = require("../models/resumeStore");
const { extractText } = require("./textExtractor");

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Contrôle les métadonnées obligatoires d'un CV. Retourne { valid, errors }.
function validateResume(resume) {
  const errors = [];

  if (!isNonEmptyString(resume.profileId)) {
    errors.push("Le profil associé est obligatoire");
  }
  if (!isNonEmptyString(resume.name)) errors.push("Le nom du CV est obligatoire");
  if (!RESUME_FORMATS.includes(resume.format)) {
    errors.push("Le format du CV est invalide");
  }
  if (!isNonEmptyString(resume.sourcePath)) {
    errors.push("Le chemin source est obligatoire");
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// Importe un CV pour un profil : valide les métadonnées, extrait le texte
// (TXT/MD réels ; PDF/DOCX → UnsupportedFormatError), fixe le CV par défaut
// si c'est le premier du profil, puis persiste. Retourne le CV enregistré.
function importResume(input, filePath = DEFAULT_PATH) {
  const format = input.format ?? formatFromPath(input.sourcePath);

  // Valide les métadonnées avant toute lecture de fichier.
  const draft = createResume({ ...input, format });
  const validation = validateResume(draft);
  if (!validation.valid) {
    throw new Error(validation.errors.join(", "));
  }

  // Extraction du contenu ; lève UnsupportedFormatError pour PDF/DOCX.
  const extractedText = extractText(draft.sourcePath);
  if (!isNonEmptyString(extractedText)) {
    throw new Error("Le CV est vide ou illisible");
  }

  // Premier CV non archivé du profil → défaut automatique.
  const existing = loadResumes(filePath).filter(
    (r) => r.profileId === draft.profileId && !r.archived,
  );
  const isDefault = existing.length === 0;

  const resume = createResume({ ...draft, extractedText, isDefault });
  return saveResume(resume, filePath);
}

// Définit le CV par défaut d'un profil, en garantissant un seul défaut.
// Lève une erreur si le CV n'appartient pas au profil.
function setDefaultResume(profileId, resumeId, filePath = DEFAULT_PATH) {
  const resumes = loadResumes(filePath);
  let target = null;

  for (const resume of resumes) {
    if (resume.profileId !== profileId) continue;
    if (resume.id === resumeId) {
      resume.isDefault = true;
      target = resume;
    } else if (resume.isDefault) {
      resume.isDefault = false;
    }
  }

  if (!target) throw new Error("CV introuvable pour ce profil");

  saveResumes(resumes, filePath);
  return target;
}

module.exports = {
  validateResume,
  importResume,
  setDefaultResume,
};
