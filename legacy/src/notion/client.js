// Charge les variables d'environnement depuis .env.local (secrets gitignorés).
require("dotenv").config({ path: ".env.local" });

const { Client } = require("@notionhq/client");

const notion = new Client({
  auth: process.env.NOTION_TOKEN,
});

module.exports = notion;
