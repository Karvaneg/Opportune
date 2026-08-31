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

// Un ticket est « urgent » à partir de ce score (max possible = 6).
const URGENT_THRESHOLD = 5;

// Signaux d'urgence pour proposer une priorité (heuristique, ajustable).
const PHASE_WEIGHT = { MVP: 2, V1: 1, V2: 0 };
const TYPE_WEIGHT = { Bug: 2 };

// Traduction poids cumulé -> priorité proposée.
function weightToPriority(weight) {
  if (weight >= 4) return "P0";
  if (weight === 3) return "P1";
  if (weight === 2) return "P2";
  return "P3";
}

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
 * Renvoie les tickets urgents (non terminés, score >= seuil), triés par score.
 * @param {Array} tickets
 * @param {number} [threshold=URGENT_THRESHOLD]
 * @returns {Array} tickets enrichis de `score`
 */
function getUrgentTickets(tickets, threshold = URGENT_THRESHOLD) {
  return tickets
    .filter((ticket) => !DONE_STATUSES.has(ticket.statut))
    .map((ticket) => ({ ...ticket, score: scoreTicket(ticket) }))
    .filter((ticket) => ticket.score >= threshold)
    .sort((a, b) => b.score - a.score);
}

/**
 * Propose une priorité P0–P3 à partir de signaux du ticket (phase, type).
 * Heuristique de départ, destinée à être affinée.
 * @param {object} ticket
 * @returns {string} "P0" | "P1" | "P2" | "P3"
 */
function suggestPriority(ticket) {
  const weight = (PHASE_WEIGHT[ticket.phase] ?? 0) + (TYPE_WEIGHT[ticket.type] ?? 0);
  return weightToPriority(weight);
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
  getUrgentTickets,
  suggestPriority,
  explainRecommendation,
};
