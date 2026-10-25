// Formatage des tickets pour le terminal.
// Pur : renvoie du texte, n'écrit rien lui-même (aucun console.log).

const DASH = "—";
const INDENT = " ".repeat(16); // aligne la ligne meta sous le titre

// Une ligne principale + une ligne meta pour un ticket.
function formatTicket(t) {
  const prio = (t.priorite ?? DASH).padEnd(2);
  const id = (t.id ?? DASH).padEnd(8);
  const meta = `${t.epic ?? DASH} · est. ${t.estimation ?? DASH}`;
  return `  ${prio}  ${id}  ${t.titre ?? DASH}\n${INDENT}${meta}`;
}

/**
 * Produit le rendu texte d'une liste de tickets.
 *
 * @param {Array} tickets
 * @param {object} [options]
 * @param {string} [options.titre] - libellé affiché dans l'en-tête
 * @returns {string}
 */
function formatTickets(tickets, { titre = "Tickets" } = {}) {
  if (tickets.length === 0) return `Aucun ticket · ${titre}`;
  const entete = `📋 ${tickets.length} ticket(s) · ${titre}\n`;
  return [entete, ...tickets.map(formatTicket)].join("\n");
}

module.exports = { formatTicket, formatTickets };
