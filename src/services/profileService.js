// Validation du profil candidat avant l'analyse des offres.
const { CONTRACT_TYPES } = require("../models/userProfile");

// Vérifie les champs obligatoires. Retourne { valid, errors }.
function validateProfile(profile) {
  const errors = [];

  if (!profile.name) errors.push("Le nom est obligatoire");

  if (!Array.isArray(profile.skills) || profile.skills.length === 0) {
    errors.push("Au moins une compétence est obligatoire");
  }

  if (!CONTRACT_TYPES.includes(profile.contractType)) {
    errors.push("Le type de contrat est invalide");
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

module.exports = {
  validateProfile,
};
