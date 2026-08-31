// Moteur de recommandation d'Opportune.
// Décide quel ticket traiter en priorité à partir de son statut et de sa priorité.

// Barème de priorité : P0 (le plus urgent) pèse le plus lourd.
const PRIORITY_SCORES = { P0: 4, P1: 3, P2: 2, P3: 1 };

// Barème de statut : un ticket pas encore démarré passe avant un ticket en cours.
const STATUS_SCORES = {
  Ready: 2, // prêt à démarrer
  Backlog: 2, // à faire
  "In Progress": 1, // en cours
  Review: 1, // en cours de relecture
};

// Statuts considérés comme terminés (exclus des recommandations).
const DONE_STATUSES = new Set(["Done"]);

/**
 * Attribue un score d'urgence à un ticket (plus haut = plus prioritaire).
 * @param {object} ticket
 * @returns {number}
 */
function scoreTicket(ticket) {
  const priorityScore = PRIORITY_SCORES[ticket.priorite] ?? 0;
  const statusScore = STATUS_SCORES[ticket.statut] ?? 0;
  return priorityScore + statusScore;
}

/**
 * Recommande le prochain ticket à traiter parmi les tickets non terminés.
 * @param {Array} tickets
 * @returns {object|null} le ticket recommandé (enrichi de `score`), ou null
 */
function recommendNextTicket(tickets) {
  const [meilleur = null] = tickets
    .filter((ticket) => !DONE_STATUSES.has(ticket.statut))
    .map((ticket) => ({ ...ticket, score: scoreTicket(ticket) }))
    .sort((a, b) => b.score - a.score);

  return meilleur;
}

/**
 * Explique brièvement pourquoi un ticket est recommandé.
 * @param {object} ticket - ticket enrichi de `score`
 * @returns {string}
 */
function explainRecommendation(ticket) {
  if (!ticket) return "Aucun ticket actionnable : tout est terminé. 🎉";
  return `Priorité ${ticket.priorite ?? "—"} et statut « ${ticket.statut ?? "—"} » → score ${ticket.score}.`;
}

module.exports = {
  scoreTicket,
  recommendNextTicket,
  explainRecommendation,
};
