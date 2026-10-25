const notion = require("./client");
const { write, toTicket } = require("./mappers");

/**
 * Modifie le statut d'un ticket.
 *
 * @param {string} pageId - identifiant de la page Notion (champ `pageId` d'un ticket)
 * @param {string} statut - nouveau statut, ex. "Backlog", "In Progress", "Done"
 * @returns {Promise<object>} le ticket normalisé après mise à jour
 */
async function updateTicketStatus(pageId, statut) {
  const page = await notion.pages.update({
    page_id: pageId,
    properties: { Statut: write.status(statut) },
  });
  return toTicket(page);
}

module.exports = { updateTicketStatus };
