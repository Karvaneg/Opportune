// Import et validation des CV d'un profil candidat.
const {
  RESUME_FORMATS,
  formatFromPath,
  createResume,
  updateResume,
} = require("../models/resume");
const {
  DEFAULT_PATH,
  loadResumes,
  saveResume,
  saveResumes,
} = require("../models/resumeStore");
const { extractText } = require("./textExtractor");
const { ValidationError, NotFoundError } = require("../errors");

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
    throw new ValidationError(validation.errors.join(", "));
  }

  // Extraction du contenu ; lève UnsupportedFormatError pour PDF/DOCX.
  const extractedText = extractText(draft.sourcePath);
  if (!isNonEmptyString(extractedText)) {
    throw new ValidationError("Le CV est vide ou illisible");
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

  if (!target) throw new NotFoundError("CV introuvable pour ce profil");

  saveResumes(resumes, filePath);
  return target;
}

// Liste les CV d'un profil (les archivés sont exclus par défaut).
function listResumes(profileId, options = {}, filePath = DEFAULT_PATH) {
  const { includeArchived = false } = options;
  return loadResumes(filePath).filter(
    (r) => r.profileId === profileId && (includeArchived || !r.archived),
  );
}

// Retourne un CV par son id, ou null s'il n'existe pas.
function getResume(id, filePath = DEFAULT_PATH) {
  return loadResumes(filePath).find((r) => r.id === id) ?? null;
}

// Remplace le contenu d'un CV (nouvelle source) en conservant id, nom et statut
// de défaut. Ré-extrait le texte (PDF/DOCX → UnsupportedFormatError).
function replaceResume(id, newSourcePath, filePath = DEFAULT_PATH) {
  const resumes = loadResumes(filePath);
  const index = resumes.findIndex((r) => r.id === id);
  if (index < 0) throw new NotFoundError("CV introuvable");

  const extractedText = extractText(newSourcePath);
  if (!isNonEmptyString(extractedText)) {
    throw new ValidationError("Le CV est vide ou illisible");
  }

  const updated = updateResume(resumes[index], {
    sourcePath: newSourcePath,
    format: formatFromPath(newSourcePath),
    extractedText,
    importedAt: new Date().toISOString(),
  });

  resumes[index] = updated;
  saveResumes(resumes, filePath);
  return updated;
}

// Prépare le retrait (archivage/suppression) d'un CV par défaut : si d'autres
// CV actifs subsistent, l'appelant DOIT désigner le nouveau défaut (newDefaultId),
// sinon une erreur explicite est levée (l'UI posera la question à l'utilisateur).
// Si c'était le dernier CV actif, il n'y a rien à réassigner.
function reassignDefaultOrThrow(resumes, target, newDefaultId) {
  const others = resumes.filter(
    (r) => r.profileId === target.profileId && !r.archived && r.id !== target.id,
  );
  if (others.length === 0) return; // dernier CV actif : aucun défaut à réassigner

  if (!newDefaultId) {
    throw new ValidationError(
      "Ce CV est le CV par défaut : désignez le nouveau CV par défaut (newDefaultId).",
    );
  }
  const next = others.find((r) => r.id === newDefaultId);
  if (!next) throw new NotFoundError("Le nouveau CV par défaut désigné est introuvable ou archivé");
  next.isDefault = true;
}

// Archive un CV (conservé dans l'historique, mais retiré des listes actives).
function archiveResume(id, options = {}, filePath = DEFAULT_PATH) {
  const resumes = loadResumes(filePath);
  const target = resumes.find((r) => r.id === id);
  if (!target) throw new NotFoundError("CV introuvable");

  if (target.isDefault) {
    reassignDefaultOrThrow(resumes, target, options.newDefaultId);
    target.isDefault = false;
  }
  target.archived = true;

  saveResumes(resumes, filePath);
  return target;
}

// Supprime définitivement un CV de la collection.
function deleteResume(id, options = {}, filePath = DEFAULT_PATH) {
  const resumes = loadResumes(filePath);
  const target = resumes.find((r) => r.id === id);
  if (!target) throw new NotFoundError("CV introuvable");

  if (target.isDefault) {
    reassignDefaultOrThrow(resumes, target, options.newDefaultId);
  }

  saveResumes(resumes.filter((r) => r.id !== id), filePath);
  return target;
}

module.exports = {
  validateResume,
  importResume,
  setDefaultResume,
  listResumes,
  getResume,
  replaceResume,
  archiveResume,
  deleteResume,
};
