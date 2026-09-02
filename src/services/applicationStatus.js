// Machine à états du suivi des candidatures : transitions autorisées entre les
// statuts de l'échelle (application.js). Logique pure, sans persistance —
// utilisée par applicationService pour contrôler les changements de statut.
const { APPLICATION_STATUSES } = require("../models/application");

// Transitions autorisées depuis chaque statut. Les statuts finaux (Refusée,
// Acceptée, Abandonnée) n'ont aucune suite. « Abandonnée » reste accessible tant
// que la candidature n'est pas déjà dans un état final.
const STATUS_TRANSITIONS = {
  "À étudier": ["Validée", "Abandonnée"],
  "Validée": ["Envoyée", "Abandonnée"],
  "Envoyée": ["Entretien", "Refusée", "Abandonnée"],
  "Entretien": ["Acceptée", "Refusée", "Abandonnée"],
  "Refusée": [],
  "Acceptée": [],
  "Abandonnée": [],
};

// Vrai si le statut appartient à l'échelle fermée.
function isValidStatus(status) {
  return APPLICATION_STATUSES.includes(status);
}

// Statuts atteignables depuis `status` (liste vide si statut final ou inconnu).
function nextStatuses(status) {
  return STATUS_TRANSITIONS[status] ?? [];
}

// Vrai si la transition from → to est autorisée.
function canTransition(from, to) {
  return nextStatuses(from).includes(to);
}

// Vrai si le statut est final (valide et sans transition sortante).
function isTerminal(status) {
  return isValidStatus(status) && nextStatuses(status).length === 0;
}

module.exports = {
  STATUS_TRANSITIONS,
  isValidStatus,
  nextStatuses,
  canTransition,
  isTerminal,
};
