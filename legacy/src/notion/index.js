// Point d'entrée public du module Notion.
// Les consommateurs importent depuis "./notion", sans connaître l'organisation interne.
module.exports = {
  ...require("./tickets"),
  ...require("./mutations"),
};
