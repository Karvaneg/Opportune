const notion = require("./client");
const { buildFilter } = require("./filters");
const { toTicket } = require("./mappers");

const DATA_SOURCE_ID = process.env.NOTION_DATA_SOURCE_ID;

/**
 * Lit les tickets de la base Notion, avec filtres optionnels et combinables.
 *
 * @param {object} [filtres]
 * @param {string} [filtres.statut]   - ex. "Backlog", "In Progress", "Done"
 * @param {string} [filtres.priorite] - ex. "P0", "P1", "P2", "P3"
 * @param {string} [filtres.phase]    - ex. "MVP", "V1", "V2"
 * @returns {Promise<Array>} liste de tickets normalisés
 */
async function getTickets(filtres = {}) {
  const filter = buildFilter(filtres);
  const tickets = [];
  let cursor;

  // Pagination : Notion renvoie 100 résultats max par requête.
  do {
    const response = await notion.dataSources.query({
      data_source_id: DATA_SOURCE_ID,
      filter,
      start_cursor: cursor,
    });
    tickets.push(...response.results.map(toTicket));
    cursor = response.has_more ? response.next_cursor : undefined;
  } while (cursor);

  return tickets;
}

module.exports = { getTickets };
