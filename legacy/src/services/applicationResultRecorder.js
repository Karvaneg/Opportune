// Enregistrement des résultats de candidature (OPP-064). Critère : les réponses
// permettent d'améliorer le scoring futur. On enregistre l'issue d'une
// candidature (acceptée, entretien, refusée, sans réponse) en capturant un
// instantané du score d'adéquation au moment de la candidature. Les couples
// { score → issue } forment la boucle de feedback exploitable pour calibrer le
// scoring futur (analyzeScoreCalibration). Logique déterministe, sans LLM.
const {
  getApplication,
  updateApplicationById,
  listApplications,
} = require("./applicationService");
const { DEFAULT_PATH } = require("../models/applicationStore");
const { ValidationError, NotFoundError } = require("../errors");

// Issues possibles d'une candidature (réponse observée).
const RESULT_OUTCOMES = ["accepted", "interview", "rejected", "no_response"];

// Issues considérées comme un signal positif (bon appariement offre/profil).
const POSITIVE_OUTCOMES = ["accepted", "interview"];

// Vrai si la valeur est une date interprétable (chaîne non vide et parseable).
function isValidDateString(value) {
  return typeof value === "string" && value.trim() !== "" && !Number.isNaN(Date.parse(value));
}

// Vrai si l'issue est un signal positif.
function isPositiveOutcome(outcome) {
  return POSITIVE_OUTCOMES.includes(outcome);
}

// Enregistre le résultat d'une candidature. Capture un instantané du score de la
// candidature (source du feedback de scoring). Persiste application.result et
// retourne la candidature à jour.
function recordResult(applicationId, { outcome, respondedAt = null, note = null } = {}, filePath = DEFAULT_PATH) {
  if (!RESULT_OUTCOMES.includes(outcome)) {
    throw new ValidationError(
      `Résultat invalide : ${outcome} (attendu ${RESULT_OUTCOMES.join(", ")})`,
    );
  }
  if (respondedAt !== null && !isValidDateString(respondedAt)) {
    throw new ValidationError("Date de réponse invalide");
  }

  const application = getApplication(applicationId, filePath);
  if (!application) throw new NotFoundError("Candidature introuvable");

  const result = {
    outcome,
    respondedAt: respondedAt ?? new Date().toISOString().slice(0, 10),
    note,
    // Instantané du score au moment de la candidature : socle du feedback scoring.
    score: typeof application.score === "number" ? application.score : null,
  };

  return updateApplicationById(applicationId, { result }, filePath);
}

// Construit le jeu de données de feedback pour améliorer le scoring futur : pour
// chaque candidature d'un profil ayant un résultat enregistré et un score
// numérique, associe le score à l'issue observée.
function buildScoringFeedback(profileId, filePath = DEFAULT_PATH) {
  return listApplications(profileId, filePath)
    .filter((a) => a.result && typeof a.result.score === "number")
    .map((a) => ({
      applicationId: a.id,
      offerId: a.offerId,
      score: a.result.score,
      outcome: a.result.outcome,
      positive: isPositiveOutcome(a.result.outcome),
    }));
}

// Analyse la calibration du scoring à partir du feedback : score moyen des
// candidatures à issue positive vs négative. Un scoring bien calibré donne un
// score moyen plus élevé aux issues positives — base pour l'ajuster.
function analyzeScoreCalibration(feedback = []) {
  const summarize = (items) => ({
    count: items.length,
    averageScore: items.length > 0 ? items.reduce((sum, i) => sum + i.score, 0) / items.length : null,
  });

  return {
    positive: summarize(feedback.filter((f) => f.positive)),
    negative: summarize(feedback.filter((f) => !f.positive)),
  };
}

module.exports = {
  RESULT_OUTCOMES,
  POSITIVE_OUTCOMES,
  isPositiveOutcome,
  recordResult,
  buildScoringFeedback,
  analyzeScoreCalibration,
};
