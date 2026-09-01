// Point d'entrée public des services (l'intelligence d'Opportune).
module.exports = {
  ...require("./opportuneService"),
  ...require("./profileService"),
  ...require("./offerService"),
  ...require("./resumeService"),
  ...require("./textExtractor"),
  ...require("./skillService"),
};
