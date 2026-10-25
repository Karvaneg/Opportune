// Modèle d'un CV (version) rattaché à un profil candidat : structure, valeurs
// par défaut, construction et mise à jour. La validation et l'import vivent
// dans src/services/resumeService.js ; l'extraction dans textExtractor.js ;
// la persistance dans src/models/resumeStore.js.
const { randomUUID } = require("node:crypto");
const path = require("node:path");

// Tous les formats reconnus par le modèle.
const RESUME_FORMATS = ["TXT", "MD", "PDF", "DOCX"];

// Formats dont l'extraction de texte est réellement supportée (cf. textExtractor).
// PDF et DOCX sont reconnus mais pas encore extractibles → refusés proprement.
const SUPPORTED_FORMATS = ["TXT", "MD"];

// Champs obligatoires pour qu'un CV soit exploitable.
const REQUIRED_FIELDS = ["profileId", "name", "format", "sourcePath"];

// Déduit le format (TXT|MD|PDF|DOCX) depuis l'extension du chemin.
// Retourne null si l'extension n'est pas reconnue.
function formatFromPath(filePath) {
  const ext = path.extname(String(filePath ?? "")).toLowerCase();
  const map = { ".txt": "TXT", ".md": "MD", ".pdf": "PDF", ".docx": "DOCX" };
  return map[ext] ?? null;
}

// Construit un CV complet à partir de données partielles.
// Un id est généré si absent ; importedAt est daté à la construction.
function createResume(data = {}) {
  return {
    id: data.id ?? randomUUID(),
    profileId: data.profileId ?? null, // référence du profil — obligatoire
    name: data.name ?? "", // nom explicite — obligatoire
    format: data.format ?? null, // TXT | MD | PDF | DOCX — obligatoire
    sourcePath: data.sourcePath ?? null, // chemin interne du fichier — jamais exposé
    extractedText: data.extractedText ?? "", // contenu textuel extrait
    importedAt: data.importedAt ?? new Date().toISOString(),
    isDefault: data.isDefault ?? false,
    archived: data.archived ?? false,
  };
}

// Retourne une copie du CV avec les modifications appliquées (immutable).
// L'id reste stable (il identifie le CV en persistance).
function updateResume(resume, changes = {}) {
  return { ...resume, ...changes, id: resume.id };
}

// Vue publique d'un CV : masque sourcePath (chemin interne, jamais exposé
// comme contenu utilisateur).
function toPublicView(resume) {
  const { sourcePath, ...pub } = resume;
  return pub;
}

module.exports = {
  RESUME_FORMATS,
  SUPPORTED_FORMATS,
  REQUIRED_FIELDS,
  formatFromPath,
  createResume,
  updateResume,
  toPublicView,
};
