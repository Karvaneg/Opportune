// Normalisation des offres : convertit une offre « brute » (issue de n'importe
// quelle source, aux champs hétérogènes) vers le modèle interne jobOffer.
// Harmonise les champs, normalise le type de contrat, marque les champs absents
// à null, et conserve la source et les données brutes d'origine (champ raw).
const { OFFER_CONTRACT_TYPES, createOffer } = require("../models/jobOffer");

// Synonymes de types de contrat (clé en minuscules) → valeur canonique.
const CONTRACT_SYNONYMS = {
  "c.d.i": "CDI",
  "contrat à durée indéterminée": "CDI",
  permanent: "CDI",
  "c.d.d": "CDD",
  "contrat à durée déterminée": "CDD",
  "free-lance": "FREELANCE",
  "indépendant": "FREELANCE",
  independant: "FREELANCE",
  independent: "FREELANCE",
  contractor: "FREELANCE",
  consultant: "FREELANCE",
  mission: "FREELANCE",
};

// Normalise un type de contrat vers CDI / CDD / FREELANCE.
// Retourne null si non reconnu (champ non renseigné).
function normalizeContractType(value) {
  if (typeof value !== "string") return null;
  const key = value.trim().toLowerCase();
  if (key === "") return null;

  const canonical = key.toUpperCase();
  if (OFFER_CONTRACT_TYPES.includes(canonical)) return canonical;
  return CONTRACT_SYNONYMS[key] ?? null;
}

// Nettoie une valeur : chaîne trimée (null si vide), null si absente,
// valeur inchangée sinon.
function cleanString(value) {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

// Renvoie le premier des alias présent (non vide) dans l'objet brut.
function pick(raw, ...keys) {
  for (const key of keys) {
    const value = raw[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

// Normalise une offre brute vers le modèle jobOffer. Les données brutes sont
// conservées dans le champ raw. N'effectue pas de validation (à faire ensuite
// via validateOffer) : une offre normalisée peut rester incomplète.
function normalizeOffer(raw = {}) {
  return createOffer({
    id: raw.id,
    title: cleanString(pick(raw, "title", "titre", "poste", "jobTitle")),
    company: cleanString(pick(raw, "company", "entreprise", "employer", "client")),
    source: cleanString(pick(raw, "source")),
    url: cleanString(pick(raw, "url", "lien", "link")),
    contractType: normalizeContractType(pick(raw, "contractType", "contract", "typeContrat", "type")),
    location: cleanString(pick(raw, "location", "localisation", "lieu", "ville")),
    compensation: cleanString(pick(raw, "compensation", "salaire", "salary", "tjm", "budget")),
    description: cleanString(pick(raw, "description")),
    publishedAt: cleanString(pick(raw, "publishedAt", "datePublication", "date")),
    raw,
  });
}

// Normalise une liste d'offres brutes.
function normalizeOffers(rawOffers = []) {
  return rawOffers.map(normalizeOffer);
}

module.exports = { normalizeContractType, normalizeOffer, normalizeOffers };
