// Classification d'une opportunité (OPP-034) : range une offre dans l'une des
// catégories CDI / CDD / Freelance / À ignorer, en tenant compte des préférences
// de contrat du profil. Déterministe, sans LLM.
//
// Règle : la catégorie reflète le type de contrat de l'offre, sauf s'il est
// inconnu ou incompatible avec les préférences du profil → « À ignorer ». La
// compatibilité réutilise compareContractType (source unique de vérité).
const { compareContractType } = require("./offerProfileComparator");

// Catégories possibles (échelle fermée).
const OPPORTUNITY_CATEGORIES = ["CDI", "CDD", "Freelance", "À ignorer"];

const IGNORE = "À ignorer";

// Type de contrat de l'offre (majuscules) → catégorie affichable.
const TYPE_TO_CATEGORY = { CDI: "CDI", CDD: "CDD", FREELANCE: "Freelance" };

// Classe une offre (ou ses informations clés) vis-à-vis d'un profil.
// - type de contrat absent ou non reconnu → « À ignorer » ;
// - type reconnu mais hors préférences du profil → « À ignorer » ;
// - sinon → CDI / CDD / Freelance. Un profil sans préférence de contrat ne filtre
//   pas : l'offre est classée selon son type.
function classifyOpportunity(offer = {}, profile = {}) {
  const category = TYPE_TO_CATEGORY[offer.contractType];
  if (!category) return IGNORE; // type absent ou non reconnu

  // compatible === false → hors préférences explicites → à ignorer.
  // compatible === true (préférence satisfaite) ou null (profil sans préférence) → on garde.
  if (compareContractType(offer.contractType, profile).compatible === false) return IGNORE;

  return category;
}

module.exports = { OPPORTUNITY_CATEGORIES, classifyOpportunity };
