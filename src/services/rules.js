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
// Poids max cumulé = 2 (phase) + 2 (type) + 1 (epic) + 1 (quick win) = 6.
const PHASE_WEIGHT = { MVP: 2, V1: 1, V2: 0 };
const TYPE_WEIGHT = { Bug: 2, Technique: 1 };
const EPIC_WEIGHT = { "Epic E7 — Infrastructure et sécurité": 1 };

// Quick win : un petit ticket mérite un léger coup de pouce.
const QUICK_WIN_ESTIMATIONS = new Set(["1", "2"]);
const QUICK_WIN_BONUS = 1;

// Traduction du poids cumulé -> priorité proposée (échelle 0–6).
function weightToPriority(weight) {
  if (weight >= 5) return "P0";
  if (weight >= 3) return "P1";
  if (weight >= 1) return "P2";
  return "P3";
}

module.exports = {
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
};
