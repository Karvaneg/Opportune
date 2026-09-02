// Modèle d'une candidature : relie un candidat (profil) à une offre, avec les
// documents utilisés, le suivi (statut, contact, prochaine action) et le score
// d'adéquation au moment de la candidature. La validation vit dans
// src/services/applicationService.js ; la persistance dans applicationStore.js.
const { randomUUID } = require("node:crypto");

// Échelle fermée des statuts de suivi d'une candidature (ordre du cycle de vie).
// Les transitions autorisées entre statuts vivent dans applicationStatus.js.
const APPLICATION_STATUSES = [
  "À étudier",
  "Validée",
  "Envoyée",
  "Entretien",
  "Refusée",
  "Acceptée",
  "Abandonnée",
];

// Statut initial d'une candidature (premier de l'échelle).
const DEFAULT_STATUS = APPLICATION_STATUSES[0];

// Champs obligatoires : une candidature relie forcément un profil à une offre.
const REQUIRED_FIELDS = ["profileId", "offerId"];

// Construit une candidature complète à partir de données partielles.
// Un id est généré si absent ; createdAt/updatedAt sont datés à la construction.
function createApplication(data = {}) {
  const now = new Date().toISOString();
  return {
    id: data.id ?? randomUUID(),
    profileId: data.profileId ?? null, // candidat — obligatoire
    offerId: data.offerId ?? null, // offre associée — obligatoire
    status: data.status ?? DEFAULT_STATUS, // statut de suivi
    score: data.score ?? null, // score d'adéquation (0-100) au moment de la candidature
    documents: data.documents ?? [], // documents utilisés : [{ type, ref }] (CV adapté, lettre…)
    contact: data.contact ?? null, // contact recruteur : { name, email… } ou null
    nextAction: data.nextAction ?? null, // prochaine action à mener
    appliedAt: data.appliedAt ?? null, // date d'envoi (null tant que non envoyée)
    followUpAt: data.followUpAt ?? null, // date de relance planifiée (auto ou manuelle), null si aucune
    createdAt: data.createdAt ?? now,
    updatedAt: data.updatedAt ?? now,
  };
}

// Retourne une copie de la candidature avec les modifications appliquées
// (immutable). L'id reste stable ; updatedAt est rafraîchi.
function updateApplication(application, changes = {}) {
  return {
    ...application,
    ...changes,
    id: application.id,
    updatedAt: new Date().toISOString(),
  };
}

module.exports = {
  APPLICATION_STATUSES,
  DEFAULT_STATUS,
  REQUIRED_FIELDS,
  createApplication,
  updateApplication,
};
