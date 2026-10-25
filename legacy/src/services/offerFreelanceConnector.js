// Connecteur de plateforme freelance (OPP-023). Spécialisation du connecteur de
// source générique (OPP-022) : force le type de contrat FREELANCE et enrichit
// chaque mission des détails propres au freelance (budget, TJM, durée,
// disponibilité) extraits des données brutes.
//
// Choix de conception : le modèle jobOffer (OPP-020) n'est pas étendu. Les
// détails freelance sont attachés additivement sous le champ `freelance` des
// missions retournées (jamais dans le modèle partagé), et restent tracés dans
// `raw`. La normalisation, la validation, la conservation url/source et la
// journalisation sont assurées par le connecteur générique sous-jacent.
const { createSourceConnector } = require("./offerSourceConnector");
const { ValidationError } = require("../errors");

// Nettoie une valeur : chaîne trimée (null si vide), null si absente.
function cleanString(value) {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

// Renvoie le premier alias présent (non vide) dans l'objet brut.
function pick(raw, ...keys) {
  for (const key of keys) {
    const value = raw[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

// Extrait les détails propres à une mission freelance depuis ses données brutes.
// Chaque champ absent vaut null (« extraits lorsque disponibles »).
function extractFreelanceDetails(raw = {}) {
  return {
    budget: cleanString(pick(raw, "budget", "enveloppe")),
    tjm: cleanString(pick(raw, "tjm", "dailyRate", "tauxJournalier", "taux")),
    duration: cleanString(pick(raw, "duration", "durée", "duree", "dureeMission", "length")),
    availability: cleanString(
      pick(raw, "availability", "disponibilité", "disponibilite", "startDate", "dateDebut", "démarrage", "demarrage"),
    ),
  };
}

// Crée un connecteur pour une plateforme freelance donnée. Preset du connecteur
// générique : type de contrat forcé à FREELANCE, missions enrichies de leurs
// détails freelance.
// - platform : identifiant de la plateforme (obligatoire), reporté en source.
// - fetcher : fonction (sync ou async) renvoyant un tableau de missions brutes.
// - logger : cible de journalisation (défaut console).
function createFreelanceConnector(config = {}) {
  const { platform, fetcher, logger } = config;

  if (typeof platform !== "string" || platform.trim() === "") {
    throw new ValidationError("Le connecteur freelance exige une plateforme (platform)");
  }

  const base = createSourceConnector({
    name: platform,
    fetcher,
    contractType: "FREELANCE",
    logger,
  });

  // Récupère les missions puis attache leurs détails freelance. Le format de
  // retour reste { offers, skipped } ; chaque mission porte un champ `freelance`.
  async function fetchOffers(params) {
    const { offers, skipped } = await base.fetchOffers(params);
    return {
      offers: offers.map((offer) => ({ ...offer, freelance: extractFreelanceDetails(offer.raw) })),
      skipped,
    };
  }

  return { platform: base.name, contractType: base.contractType, fetchOffers };
}

module.exports = { createFreelanceConnector, extractFreelanceDetails };
