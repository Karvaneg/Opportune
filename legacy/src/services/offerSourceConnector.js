// Connecteur de source d'offres (OPP-022). Récupère automatiquement des offres
// depuis une source externe via un *fetcher* injectable : le fetcher fournit les
// données brutes (aucun accès réseau ici — l'adaptateur réseau réel fera l'objet
// d'un ticket dédié, cf. cap « zéro dépendance / testable »).
//
// Le connecteur normalise chaque offre brute vers le modèle jobOffer (OPP-020),
// force la source d'origine (le nom du connecteur) et conserve l'URL et les
// données brutes. Les offres invalides sont écartées sans interrompre le lot ;
// un filtre optionnel de type de contrat permet de cibler une source CDI. Les
// erreurs (récupération et validation) sont journalisées.
const { normalizeOffer } = require("./offerNormalizer");
const { validateOffer } = require("./offerService");
const { OFFER_CONTRACT_TYPES } = require("../models/jobOffer");
const { ValidationError } = require("../errors");
const { logger: defaultLogger } = require("../logging");

// Crée un connecteur configuré pour une source donnée.
// - name : identifiant de la source (obligatoire), reporté dans chaque offre.
// - fetcher : fonction (sync ou async) renvoyant un tableau d'offres brutes.
// - contractType : filtre optionnel (ex. "CDI") — seules les offres de ce type
//   sont retenues. null = pas de filtre.
// - logger : cible de journalisation (défaut : logger applicatif), doit exposer .error.
function createSourceConnector(config = {}) {
  const { name, fetcher, contractType = null, logger = defaultLogger } = config;

  if (typeof name !== "string" || name.trim() === "") {
    throw new ValidationError("Le connecteur exige un nom de source (name)");
  }
  if (typeof fetcher !== "function") {
    throw new ValidationError("Le connecteur exige un fetcher (fonction)");
  }
  if (contractType !== null && !OFFER_CONTRACT_TYPES.includes(contractType)) {
    throw new ValidationError(
      `Type de contrat de filtre invalide : ${contractType} (attendu ${OFFER_CONTRACT_TYPES.join(", ")})`,
    );
  }

  const sourceName = name.trim();

  // Récupère puis normalise les offres de la source. Best-effort : les offres
  // invalides ou hors filtre sont écartées et reportées dans `skipped`, les
  // offres exploitables (prêtes pour l'analyse et le scoring) dans `offers`.
  // Une erreur du fetcher (récupération) est journalisée puis propagée : le lot
  // entier est indisponible.
  async function fetchOffers(params) {
    let rawOffers;
    try {
      rawOffers = await fetcher(params);
    } catch (error) {
      logger.error(`[connecteur ${sourceName}] échec de récupération : ${error.message}`);
      throw error;
    }

    if (!Array.isArray(rawOffers)) {
      logger.error(`[connecteur ${sourceName}] le fetcher n'a pas renvoyé de tableau d'offres`);
      throw new ValidationError("Le fetcher doit renvoyer un tableau d'offres brutes");
    }

    const offers = [];
    const skipped = [];

    for (const raw of rawOffers) {
      // La source d'origine est imposée par le connecteur ; l'URL et les données
      // brutes sont conservées par normalizeOffer (champ raw).
      const offer = normalizeOffer({ ...raw, source: sourceName });

      const validation = validateOffer(offer);
      if (!validation.valid) {
        logger.error(
          `[connecteur ${sourceName}] offre écartée (invalide) : ${validation.errors.join(", ")}`,
        );
        skipped.push({ raw, reason: "invalid", errors: validation.errors });
        continue;
      }

      if (contractType !== null && offer.contractType !== contractType) {
        skipped.push({ raw, reason: "contractType", errors: [] });
        continue;
      }

      offers.push(offer);
    }

    return { offers, skipped };
  }

  return { name: sourceName, contractType, fetchOffers };
}

module.exports = { createSourceConnector };
