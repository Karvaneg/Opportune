// Point d'entrée public des modèles de données.
module.exports = {
  ...require("./userProfile"),
  ...require("./profileStore"),
  ...require("./jobOffer"),
  ...require("./offerStore"),
  ...require("./resume"),
  ...require("./resumeStore"),
};
