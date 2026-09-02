// Point d'entrée public des services (l'intelligence d'Opportune).
module.exports = {
  ...require("./opportuneService"),
  ...require("./profileService"),
  ...require("./offerService"),
  ...require("./offerImportService"),
  ...require("./offerNormalizer"),
  ...require("./offerDeduplicator"),
  ...require("./skillLexicon"),
  ...require("./offerKeyInfoExtractor"),
  ...require("./offerProfileComparator"),
  ...require("./resumeService"),
  ...require("./textExtractor"),
  ...require("./skillService"),
};
