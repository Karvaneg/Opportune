// Validation humaine d'une opportunité (OPP-050). Fournit le cœur *découplé* de
// l'interface de validation : la logique de décision (accepter / rejeter / mettre
// en attente) et la présentation du message de validation. Aucune dépendance à
// Discord ni au réseau — un adaptateur Discord (bot/token) se branchera par-dessus
// ces fonctions pures, testables.
const { changeApplicationStatus, getApplication } = require("./applicationService");
const { explainScore } = require("./scoreExplainer");
const { recommendAction } = require("./scoreRecommender");
const { ValidationError, NotFoundError } = require("../errors");

// Décisions possibles de la validation humaine (critère : accepter / rejeter /
// mettre en attente) + libellés et statut cible dans la machine à états.
const VALIDATION_ACTIONS = [
  { decision: "accept", label: "Accepter", status: "Validée" },
  { decision: "reject", label: "Rejeter", status: "Abandonnée" },
  { decision: "hold", label: "Mettre en attente", status: null }, // reste en l'état
];

const VALIDATION_DECISIONS = VALIDATION_ACTIONS.map((a) => a.decision);
const DECISION = Object.fromEntries(VALIDATION_ACTIONS.map((a) => [a.decision, a]));

// Applique une décision de validation à une candidature :
//   - accept → statut « Validée » ;
//   - reject → statut « Abandonnée » ;
//   - hold   → aucune transition (la candidature reste à étudier).
// Retourne la candidature à jour. Lève si la décision est inconnue, la
// candidature introuvable, ou la transition de statut non autorisée.
function reviewApplication(applicationId, decision, filePath) {
  const action = DECISION[decision];
  if (!action) {
    throw new ValidationError(`Décision de validation inconnue : ${decision} (attendu : ${VALIDATION_DECISIONS.join(", ")})`);
  }

  if (action.status === null) {
    const application = getApplication(applicationId, filePath);
    if (!application) throw new NotFoundError("Candidature introuvable");
    return application; // mise en attente : inchangée
  }

  return changeApplicationStatus(applicationId, action.status, filePath);
}

// Construit le message de validation d'une opportunité à présenter à l'humain,
// indépendamment du canal (Discord, CLI…). Agrège l'offre, le score, la
// recommandation, les raisons positives/négatives et les actions proposées.
function buildValidationMessage(offer = {}, comparison = {}) {
  const explanation = explainScore(comparison);
  const recommendation = recommendAction(explanation.score);

  return {
    title: [offer.title, offer.company].filter(Boolean).join(" — "),
    score: explanation.score,
    recommendation,
    positives: explanation.positives.map((r) => r.message),
    negatives: explanation.negatives.map((r) => r.message),
    actions: VALIDATION_ACTIONS.map(({ decision, label }) => ({ decision, label })),
  };
}

module.exports = {
  VALIDATION_ACTIONS,
  VALIDATION_DECISIONS,
  reviewApplication,
  buildValidationMessage,
};
