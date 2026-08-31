// Règles de scoring d'Opportune : barèmes et seuils, isolés de l'algorithme.
// Régler le comportement du moteur se fait ici, sans toucher à la logique.

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
const isDone = (ticket) => DONE_STATUSES.has(ticket.statut);

// Un ticket est « urgent » à partir de ce score (max possible = 6).
const URGENT_THRESHOLD = 5;

// Signaux pour proposer une priorité (heuristique, ajustable).
const PHASE_WEIGHT = { MVP: 2, V1: 1, V2: 0 };
const TYPE_WEIGHT = { Bug: 2 };

// Traduction du poids cumulé -> priorité proposée.
function weightToPriority(weight) {
  if (weight >= 4) return "P0";
  if (weight === 3) return "P1";
  if (weight === 2) return "P2";
  return "P3";
}

module.exports = {
  PRIORITY_SCORES,
  STATUS_SCORES,
  isDone,
  URGENT_THRESHOLD,
  PHASE_WEIGHT,
  TYPE_WEIGHT,
  weightToPriority,
};
