// Moteur de recommandation d'Opportune.
// Analyse les tickets pour décider lequel traiter en priorité.
// Les barèmes et seuils vivent dans ./rules.

const {
  PRIORITY_SCORES,
  STATUS_SCORES,
  isDone,
  URGENT_THRESHOLD,
  PHASE_WEIGHT,
  TYPE_WEIGHT,
  EPIC_WEIGHT,
  QUICK_WIN_ESTIMATIONS,
  QUICK_WIN_BONUS,
  weightToPriority,
} = require("./rules");

/** Score d'urgence d'un ticket (plus haut = plus prioritaire). */
function scoreTicket(ticket) {
  const priorityScore = PRIORITY_SCORES[ticket.priorite] ?? 0;
  const statusScore = STATUS_SCORES[ticket.statut] ?? 0;
  return priorityScore + statusScore;
}

/** Tickets non terminés, scorés et triés du plus urgent au moins urgent. */
function rankActionable(tickets) {
  return tickets
    .filter((ticket) => !isDone(ticket))
    .map((ticket) => ({ ...ticket, score: scoreTicket(ticket) }))
    .sort((a, b) => b.score - a.score);
}

/** Le prochain ticket à traiter (enrichi de `score`), ou null. */
function recommendNextTicket(tickets) {
  return rankActionable(tickets)[0] ?? null;
}

/** Tickets urgents : score >= seuil, triés par score. */
function getUrgentTickets(tickets, threshold = URGENT_THRESHOLD) {
  return rankActionable(tickets).filter((ticket) => ticket.score >= threshold);
}

/** Poids d'importance cumulé d'un ticket, à partir de ses signaux. */
function priorityWeight(ticket) {
  const quickWin = QUICK_WIN_ESTIMATIONS.has(ticket.estimation) ? QUICK_WIN_BONUS : 0;
  return (
    (PHASE_WEIGHT[ticket.phase] ?? 0) +
    (TYPE_WEIGHT[ticket.type] ?? 0) +
    (EPIC_WEIGHT[ticket.epic] ?? 0) +
    quickWin
  );
}

/**
 * Priorité P0–P3 proposée à partir des signaux du ticket
 * (phase, type, epic, quick win). Heuristique ajustable via ./rules.
 */
function suggestPriority(ticket) {
  return weightToPriority(priorityWeight(ticket));
}

/** Phrase expliquant la recommandation. */
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
