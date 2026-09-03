// Validation d'une offre avant analyse et scoring.
const { OFFER_CONTRACT_TYPES, createOffer, updateOffer } = require("../models/jobOffer");
const { ValidationError } = require("../errors");

// Vrai si la valeur est une chaîne non vide (espaces seuls exclus).
function isNonEmptyString(value) {
  return typeof value === "string" && value.trim() !== "";
}

// Contrôle les champs obligatoires. Retourne { valid, errors }.
function validateOffer(offer) {
  const errors = [];

  if (!isNonEmptyString(offer.title)) errors.push("Le titre est obligatoire");
  if (!isNonEmptyString(offer.company)) {
    errors.push("L'entreprise ou le client est obligatoire");
  }
  if (!isNonEmptyString(offer.source)) errors.push("La source est obligatoire");
  if (!isNonEmptyString(offer.url)) errors.push("L'URL est obligatoire");
  if (!OFFER_CONTRACT_TYPES.includes(offer.contractType)) {
    errors.push("Le type de contrat est invalide (CDI ou FREELANCE)");
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

// Construit une offre puis la valide ; lève une erreur si invalide.
function createValidOffer(data) {
  const offer = createOffer(data);
  const validation = validateOffer(offer);

  if (!validation.valid) {
    throw new ValidationError(validation.errors.join(", "));
  }

  return offer;
}

// Applique des modifications puis revalide ; lève une erreur si le résultat
// n'est plus valide (empêche de casser un champ obligatoire via une mise à jour).
function updateValidOffer(offer, changes) {
  const updated = updateOffer(offer, changes);
  const validation = validateOffer(updated);

  if (!validation.valid) {
    throw new ValidationError(validation.errors.join(", "));
  }

  return updated;
}

module.exports = {
  validateOffer,
  createValidOffer,
  updateValidOffer,
};
