// Validation du profil candidat avant l'analyse des offres.
const { CONTRACT_TYPES, createProfile } = require("../models/userProfile");

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
