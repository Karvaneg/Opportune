// Validation du profil candidat avant l'analyse des offres.
const {
  CONTRACT_TYPES,
  AVAILABILITY_OPTIONS,
  createProfile,
} = require("../models/userProfile");

// Une valeur est « fournie » si elle n'est ni null ni undefined.
const isProvided = (v) => v !== undefined && v !== null;
const isNonEmptyString = (v) => typeof v === "string" && v.trim() !== "";
const isPositiveNumber = (v) => typeof v === "number" && !Number.isNaN(v) && v >= 0;
const isIsoDate = (v) =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v));

// Disponibilité valide : une option de l'échelle fermée, ou une date ISO précise.
const isValidAvailability = (v) => AVAILABILITY_OPTIONS.includes(v) || isIsoDate(v);

// Vérifie les champs obligatoires et, s'ils sont fournis, les champs facultatifs
// (localisation, disponibilité, salaire/TJM cible). Retourne { valid, errors }.
function validateProfile(profile) {
  const errors = [];

  if (!profile.name) errors.push("Le nom est obligatoire");

  if (!Array.isArray(profile.skills) || profile.skills.length === 0) {
    errors.push("Au moins une compétence est obligatoire");
  }

  if (!CONTRACT_TYPES.includes(profile.contractType)) {
    errors.push("Le type de contrat est invalide");
  }

  // Champs facultatifs : validés uniquement s'ils sont fournis (rétrocompatibilité).
  if (isProvided(profile.location) && !isNonEmptyString(profile.location)) {
    errors.push("La localisation doit être une chaîne non vide");
  }
  if (isProvided(profile.availability) && !isValidAvailability(profile.availability)) {
    errors.push("La disponibilité est invalide");
  }
  if (isProvided(profile.targetSalary) && !isPositiveNumber(profile.targetSalary)) {
    errors.push("Le salaire cible doit être un nombre positif ou nul");
  }
  if (isProvided(profile.targetDailyRate) && !isPositiveNumber(profile.targetDailyRate)) {
    errors.push("Le TJM cible doit être un nombre positif ou nul");
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// Construit un profil puis le valide ; lève une erreur si un champ obligatoire manque.
// À utiliser quand on veut un profil garanti exploitable (ex. avant analyse des offres).
function createValidProfile(data) {
  const profile = createProfile(data);
  const validation = validateProfile(profile);

  if (!validation.valid) {
    throw new Error(validation.errors.join(", "));
  }

  return profile;
}

module.exports = {
  validateProfile,
  createValidProfile,
};
