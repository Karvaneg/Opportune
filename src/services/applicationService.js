// Validation et gestion des candidatures : création validée, persistance,
// listing par profil, récupération et mise à jour.
const {
  REQUIRED_FIELDS,
  createApplication,
  updateApplication,
} = require("../models/application");
const {
  DEFAULT_PATH,
  loadApplications,
  saveApplication,
  saveApplications,
} = require("../models/applicationStore");

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Vrai si le score est absent, ou un nombre compris entre 0 et 100.
function isValidScore(score) {
  if (score === null || score === undefined) return true;
  return typeof score === "number" && !Number.isNaN(score) && score >= 0 && score <= 100;
}

// Contrôle les champs d'une candidature. Retourne { valid, errors }.
function validateApplication(application) {
  const errors = [];

  if (!isNonEmptyString(application.profileId)) {
    errors.push("Le profil associé est obligatoire");
  }
  if (!isNonEmptyString(application.offerId)) {
    errors.push("L'offre associée est obligatoire");
  }
  if (!isValidScore(application.score)) {
    errors.push("Le score doit être compris entre 0 et 100");
  }

  return { valid: errors.length === 0, errors };
}

// Construit une candidature puis la valide ; lève une erreur si invalide.
function createValidApplication(data) {
  const application = createApplication(data);
  const validation = validateApplication(application);

  if (!validation.valid) {
    throw new Error(validation.errors.join(", "));
  }

  return application;
}

// Construit, valide puis persiste une candidature (création). Retourne l'enregistrée.
function saveValidApplication(data, filePath = DEFAULT_PATH) {
  return saveApplication(createValidApplication(data), filePath);
}

// Liste les candidatures d'un profil.
function listApplications(profileId, filePath = DEFAULT_PATH) {
  return loadApplications(filePath).filter((a) => a.profileId === profileId);
}

// Retourne une candidature par son id, ou null si elle n'existe pas.
function getApplication(id, filePath = DEFAULT_PATH) {
  return loadApplications(filePath).find((a) => a.id === id) ?? null;
}

// Applique des modifications à une candidature existante, revalide, persiste.
// Lève une erreur si la candidature est introuvable ou si le résultat est invalide.
function updateApplicationById(id, changes, filePath = DEFAULT_PATH) {
  const applications = loadApplications(filePath);
  const index = applications.findIndex((a) => a.id === id);
  if (index < 0) throw new Error("Candidature introuvable");

  const updated = updateApplication(applications[index], changes);
  const validation = validateApplication(updated);
  if (!validation.valid) {
    throw new Error(validation.errors.join(", "));
  }

  applications[index] = updated;
  saveApplications(applications, filePath);
  return updated;
}

module.exports = {
  REQUIRED_FIELDS,
  validateApplication,
  createValidApplication,
  saveValidApplication,
  listApplications,
  getApplication,
  updateApplicationById,
};
