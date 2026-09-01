// Modèle d'une offre (CDI ou freelance) : structure, valeurs par défaut,
// construction et mise à jour. La validation vit dans
// src/services/offerService.js ; la persistance dans src/models/offerStore.js.
const { randomUUID } = require("node:crypto");

// Types de contrat reconnus pour une offre (distincts du profil : ici en
// majuscules — une offre porte un seul type). La normalisation (offerNormalizer)
// mappe les variantes des sources vers ces valeurs canoniques.
const OFFER_CONTRACT_TYPES = ["CDI", "CDD", "FREELANCE"];

// Champs obligatoires pour qu'une offre soit exploitable par l'analyse.
const REQUIRED_FIELDS = ["title", "company", "source", "url", "contractType"];

// Construit une offre complète à partir de données partielles.
// Un id est généré si absent (sert de clé pour la persistance). Les champs
// absents reçoivent une valeur par défaut neutre.
function createOffer(data = {}) {
  return {
    id: data.id ?? randomUUID(),
    title: data.title ?? "", // obligatoire
    company: data.company ?? "", // entreprise ou client — obligatoire
    source: data.source ?? "", // obligatoire
    url: data.url ?? "", // obligatoire
    contractType: data.contractType ?? null, // CDI | FREELANCE — obligatoire
    location: data.location ?? null, // localisation
    compensation: data.compensation ?? null, // salaire ou budget
    description: data.description ?? null, // description
    publishedAt: data.publishedAt ?? null, // date de publication de l'offre
    importedAt: data.importedAt ?? new Date().toISOString(), // date d'import dans Opportune
    raw: data.raw ?? null, // données brutes d'origine (traçabilité, normalisation)
  };
}

// Retourne une copie de l'offre avec les modifications appliquées (immutable).
// L'id reste stable (il identifie l'offre en persistance).
function updateOffer(offer, changes = {}) {
  return { ...offer, ...changes, id: offer.id };
}

module.exports = { OFFER_CONTRACT_TYPES, REQUIRED_FIELDS, createOffer, updateOffer };
