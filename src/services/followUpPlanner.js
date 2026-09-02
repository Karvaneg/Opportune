// Planification des relances (OPP-062). Critère : une date de relance peut être
// définie automatiquement ou manuellement. La date de relance est portée par la
// candidature (application.followUpAt) et persistée via applicationService.
//
// Automatique : base = date d'envoi si disponible, sinon date de création, + un
// délai en jours (défaut 7). Manuelle : une date fournie est validée puis posée
// telle quelle. Logique déterministe, sans dépendance ni LLM.
const {
  getApplication,
  updateApplicationById,
  listApplications,
} = require("./applicationService");
const { isTerminal } = require("./applicationStatus");
const { DEFAULT_PATH } = require("../models/applicationStore");
const { ValidationError, NotFoundError } = require("../errors");

// Délai par défaut avant relance, en jours.
const DEFAULT_FOLLOW_UP_DELAY_DAYS = 7;

// Vrai si la valeur est une date interprétable (chaîne non vide et parseable).
function isValidDateString(value) {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Date.parse(value));
}

// Retourne une date ISO (YYYY-MM-DD) décalée de `days` jours par rapport à base.
function addDays(baseDate, days) {
  const d = new Date(baseDate);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// Calcule automatiquement une date de relance pour une candidature.
// Base : options.from, sinon date d'envoi, sinon date de création, sinon maintenant.
// Décalage : options.delayDays (défaut DEFAULT_FOLLOW_UP_DELAY_DAYS).
function computeFollowUpDate(application = {}, options = {}) {
  const delayDays = options.delayDays ?? DEFAULT_FOLLOW_UP_DELAY_DAYS;
  if (typeof delayDays !== "number" || Number.isNaN(delayDays) || delayDays < 0) {
    throw new ValidationError("Le délai de relance doit être un nombre de jours positif");
  }

  const base = options.from ?? application.appliedAt ?? application.createdAt ?? new Date().toISOString();
  if (!isValidDateString(base)) {
    throw new ValidationError("Date de base invalide pour le calcul de la relance");
  }

  return addDays(base, delayDays);
}

// Planifie une relance pour une candidature. Si options.date est fourni, la date
// est posée manuellement (après validation) ; sinon elle est calculée
// automatiquement. Persiste followUpAt et retourne la candidature à jour.
function planFollowUp(applicationId, options = {}, filePath = DEFAULT_PATH) {
  const application = getApplication(applicationId, filePath);
  if (!application) throw new NotFoundError("Candidature introuvable");

  let followUpAt;
  if (options.date !== undefined && options.date !== null) {
    if (!isValidDateString(options.date)) {
      throw new ValidationError("Date de relance invalide");
    }
    followUpAt = options.date; // manuelle
  } else {
    followUpAt = computeFollowUpDate(application, options); // automatique
  }

  return updateApplicationById(applicationId, { followUpAt }, filePath);
}

// Supprime la relance planifiée d'une candidature.
function clearFollowUp(applicationId, filePath = DEFAULT_PATH) {
  const application = getApplication(applicationId, filePath);
  if (!application) throw new NotFoundError("Candidature introuvable");
  return updateApplicationById(applicationId, { followUpAt: null }, filePath);
}

// Vrai si une relance est due : date de relance atteinte (≤ maintenant) et
// candidature non close (un statut final n'appelle plus de relance).
function isFollowUpDue(application = {}, now = new Date()) {
  if (!isValidDateString(application.followUpAt)) return false;
  if (isTerminal(application.status)) return false;
  const nowMs = now instanceof Date ? now.getTime() : Date.parse(now);
  return Date.parse(application.followUpAt) <= nowMs;
}

// Liste les candidatures d'un profil dont la relance est due.
function listDueFollowUps(profileId, now = new Date(), filePath = DEFAULT_PATH) {
  return listApplications(profileId, filePath).filter((a) => isFollowUpDue(a, now));
}

module.exports = {
  DEFAULT_FOLLOW_UP_DELAY_DAYS,
  computeFollowUpDate,
  planFollowUp,
  clearFollowUp,
  isFollowUpDue,
  listDueFollowUps,
};
